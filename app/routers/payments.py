import os
import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
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
    """Create a Stripe PaymentIntent and return its client_secret.

    The optional ``booking_id`` is stored alongside the intent ID so the webhook can
    later associate the successful payment with the correct booking.
    """
    try:
        # Merge any provided metadata with booking reference
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id

        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=metadata,
        )

        # Store intent details for later lookup (e.g., in webhook handling)
        _payment_intent_store[intent.id] = {
            "user_id": current_user.id,
            "booking_id": payload.booking_id,
            "metadata": metadata,
        }

        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        logger.exception("Failed to create payment intent")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe Checkout Session and return the redirect URL.

    The session includes the amount, currency and success/cancel URLs supplied by the
    client. Booking information is stored in metadata for later processing.
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

        _checkout_session_store[session.id] = {
            "user_id": current_user.id,
            "booking_id": payload.booking_id,
            "metadata": metadata,
        }

        return CheckoutSessionResponse(url=session.url)
    except Exception as exc:
        logger.exception("Failed to create checkout session")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle incoming Stripe webhook events.

    The endpoint verifies the Stripe signature using the configured webhook secret.
    It processes ``checkout.session.completed`` and ``payment_intent.succeeded``
    events, extracting the ``booking_id`` from metadata for further business
    logic (e.g., marking a booking as paid).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    try:
        if event.type == "checkout.session.completed":
            session = event.data.object  # type: ignore[attr-defined]
            booking_id = session.metadata.get("booking_id") if session.metadata else None
            logger.info(f"Checkout session completed for booking_id={booking_id}")
            # TODO: Update booking status in DB / trigger downstream actions
        elif event.type == "payment_intent.succeeded":
            intent = event.data.object  # type: ignore[attr-defined]
            booking_id = intent.metadata.get("booking_id") if intent.metadata else None
            logger.info(f"PaymentIntent succeeded for booking_id={booking_id}")
            # TODO: Update booking status in DB / trigger downstream actions
        else:
            logger.info(f"Unhandled Stripe event type: {event.type}")
    except Exception as e:
        logger.exception(f"Error processing Stripe webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook handling error")

    # Return a 200 response to acknowledge receipt of the event
    return JSONResponse(content={"status": "success"})
