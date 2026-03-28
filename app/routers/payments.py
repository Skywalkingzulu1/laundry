import os
import logging
import json
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, PositiveInt

from app.dependencies import role_required
from app.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Load Stripe configuration from environment
stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_api_key:
    # Development fallback – replace with real key in production
    stripe_api_key = "sk_test_123"
stripe.api_key = stripe_api_key

# Webhook secret for signature verification
stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# In‑memory store to map Stripe objects to booking references and status
# In a real app this would be persisted in a database.
_payment_intent_store: Dict[str, Dict[str, Any]] = {}
_checkout_session_store: Dict[str, Dict[str, Any]] = {}


class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class PaymentIntentResponse(BaseModel):
    client_secret: str


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe PaymentIntent and return its client_secret.

    The optional ``booking_id`` is stored alongside the intent ID so the webhook can
    later associate the successful payment with the correct booking.
    """
    try:
        # Include booking reference in metadata for later lookup
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=metadata,
        )
        # Record intent for later verification
        _payment_intent_store[intent.id] = {
            "user_email": current_user.email,
            "booking_id": payload.booking_id,
            "status": "created",
        }
        logger.info(
            "Created PaymentIntent %s for user %s (booking_id=%s)",
            intent.id,
            current_user.email,
            payload.booking_id,
        )
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        logger.exception("Error creating PaymentIntent: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


class CreateCheckoutSessionRequest(BaseModel):
    amount: PositiveInt
    currency: str = "usd"
    success_url: str
    cancel_url: str
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    url: str


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe Checkout Session and return the redirect URL.

    The session includes the amount as a line item and stores the optional
    ``booking_id`` in the session metadata for later webhook processing.
    """
    try:
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": payload.currency,
                        "product_data": {"name": "Laundry Service"},
                        "unit_amount": payload.amount,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            metadata=metadata,
        )
        # Record session for later verification
        _checkout_session_store[session.id] = {
            "user_email": current_user.email,
            "booking_id": payload.booking_id,
            "status": "created",
        }
        logger.info(
            "Created Checkout Session %s for user %s (booking_id=%s)",
            session.id,
            current_user.email,
            payload.booking_id,
        )
        return CheckoutSessionResponse(url=session.url)
    except Exception as exc:
        logger.exception("Error creating Checkout Session: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events.

    Verifies the signature using ``STRIPE_WEBHOOK_SECRET`` and processes
    ``payment_intent.succeeded`` and ``checkout.session.completed`` events.
    The function updates the in‑memory store and logs the outcome. In a real
    application you would update the corresponding booking record in the database.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload, sig_header=sig_header, secret=stripe_webhook_secret
            )
        except ValueError as e:
            # Invalid payload
            logger.error("Invalid payload: %s", e)
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error("Invalid signature: %s", e)
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # If no secret is set, we still parse the payload (useful for local dev)
        try:
            event = json.loads(payload)
        except Exception as e:
            logger.error("Failed to parse webhook payload: %s", e)
            raise HTTPException(status_code=400, detail="Invalid payload")

    # Process the event
    event_type = event["type"] if isinstance(event, dict) else event.type
    logger.info("Received Stripe event: %s", event_type)

    if event_type == "payment_intent.succeeded":
        intent = event["data"]["object"] if isinstance(event, dict) else event.data.object
        intent_id = intent["id"] if isinstance(intent, dict) else intent.id
        record = _payment_intent_store.get(intent_id)
        if record:
            record["status"] = "succeeded"
            logger.info(
                "PaymentIntent %s succeeded for booking %s (user %s)",
                intent_id,
                record.get("booking_id"),
                record.get("user_email"),
            )
        else:
            logger.warning("Succeeded PaymentIntent %s not found in store", intent_id)

    elif event_type == "checkout.session.completed":
        session = event["data"]["object"] if isinstance(event, dict) else event.data.object
        session_id = session["id"] if isinstance(session, dict) else session.id
        record = _checkout_session_store.get(session_id)
        if record:
            record["status"] = "completed"
            logger.info(
                "Checkout Session %s completed for booking %s (user %s)",
                session_id,
                record.get("booking_id"),
                record.get("user_email"),
            )
        else:
            logger.warning("Completed Checkout Session %s not found in store", session_id)

    # Return a 200 response to acknowledge receipt of the event
    return {"status": "success"}
