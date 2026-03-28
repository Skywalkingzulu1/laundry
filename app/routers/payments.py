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

# ---------------------------------------------------------------------------
# Stripe configuration
# ---------------------------------------------------------------------------
stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_api_key:
    # Development fallback – replace with real key in production
    stripe_api_key = "sk_test_123"
stripe.api_key = stripe_api_key

# Webhook secret for signature verification
stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# ---------------------------------------------------------------------------
# In‑memory stores (replace with persistent DB in production)
# ---------------------------------------------------------------------------
_payment_intent_store: Dict[str, Dict[str, Any]] = {}
_checkout_session_store: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class PaymentIntentResponse(BaseModel):
    client_secret: str


class CreateCheckoutSessionRequest(BaseModel):
    amount: PositiveInt
    currency: str = "usd"
    success_url: str
    cancel_url: str
    metadata: Dict[str, Any] = {}
    booking_id: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe PaymentIntent and return its client_secret.

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
        logger.exception("Error creating PaymentIntent")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe Checkout Session for one‑time payments.

    The session URL is returned to the client which should redirect the user.
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

        # Store session for later reference (e.g., webhook handling)
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
        logger.exception("Error creating Checkout Session")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint.

    Verifies the signature (if ``STRIPE_WEBHOOK_SECRET`` is set) and processes
    relevant events such as ``payment_intent.succeeded`` and
    ``checkout.session.completed``.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify signature if secret is provided
    if stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=stripe_webhook_secret,
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
        # No secret – parse without verification (useful for local testing)
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error("Unable to parse webhook JSON: %s", e)
            raise HTTPException(status_code=400, detail="Invalid JSON")

    # -----------------------------------------------------------------------
    # Event handling
    # -----------------------------------------------------------------------
    event_type = event["type"]
    logger.info("Received Stripe event: %s", event_type)

    if event_type == "payment_intent.succeeded":
        intent = event["data"]["object"]
        intent_id = intent["id"]
        store_entry = _payment_intent_store.get(intent_id)
        if store_entry:
            store_entry["status"] = "succeeded"
            logger.info(
                "PaymentIntent %s succeeded for user %s (booking_id=%s)",
                intent_id,
                store_entry["user_email"],
                store_entry.get("booking_id"),
            )
            # TODO: integrate with booking system (e.g., mark booking as paid)

    elif event_type == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session["id"]
        store_entry = _checkout_session_store.get(session_id)
        if store_entry:
            store_entry["status"] = "completed"
            logger.info(
                "Checkout Session %s completed for user %s (booking_id=%s)",
                session_id,
                store_entry["user_email"],
                store_entry.get("booking_id"),
            )
            # TODO: integrate with booking system (e.g., confirm booking)

    # Add handling for other events as needed
    # Return a 2xx response to acknowledge receipt
    return {"status": "success"}