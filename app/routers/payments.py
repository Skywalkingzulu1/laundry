import os
import json
import logging
from typing import Any, Dict, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, PositiveInt

from app.dependencies import role_required
from app.models import User

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
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

# Webhook secret for signature verification (optional – if not set we skip verification)
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

class RefundRequest(BaseModel):
    payment_intent_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    amount: Optional[PositiveInt] = None  # amount to refund (in smallest currency unit)

class RefundResponse(BaseModel):
    id: str
    status: str
    amount: int
    currency: str

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _store_payment_intent(intent: stripe.PaymentIntent, booking_id: Optional[str]):
    _payment_intent_store[intent.id] = {
        "intent": intent,
        "booking_id": booking_id,
    }
    logger.info(f"Stored PaymentIntent {intent.id} for booking {booking_id}")

def _store_checkout_session(session: stripe.checkout.Session, booking_id: Optional[str]):
    _checkout_session_store[session.id] = {
        "session": session,
        "booking_id": booking_id,
    }
    logger.info(f"Stored Checkout Session {session.id} for booking {booking_id}")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post(
    "/create-payment-intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe PaymentIntent and return its client_secret.

    The optional ``booking_id`` can be used to tie the intent to a booking.
    """
    try:
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        metadata["user_email"] = current_user.email

        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=metadata,
        )
        _store_payment_intent(intent, payload.booking_id)
        return PaymentIntentResponse(client_secret=intent.client_secret)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error while creating PaymentIntent: {e}")
        raise HTTPException(status_code=502, detail="Payment provider error")

@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe Checkout Session and return the redirect URL.

    The session is configured for a one‑time payment.
    """
    try:
        metadata = payload.metadata.copy()
        if payload.booking_id:
            metadata["booking_id"] = payload.booking_id
        metadata["user_email"] = current_user.email

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
        _store_checkout_session(session, payload.booking_id)
        return CheckoutSessionResponse(url=session.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error while creating Checkout Session: {e}")
        raise HTTPException(status_code=502, detail="Payment provider error")

@router.post(
    "/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_200_OK,
)
async def refund_payment(
    payload: RefundRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Refund a payment either by PaymentIntent ID or Checkout Session ID.
    """
    if not payload.payment_intent_id and not payload.checkout_session_id:
        raise HTTPException(status_code=400, detail="Either payment_intent_id or checkout_session_id must be provided")

    try:
        if payload.payment_intent_id:
            intent_id = payload.payment_intent_id
        else:
            # Resolve intent from checkout session
            session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
            intent_id = session.payment_intent

        refund_params: Dict[str, Any] = {"payment_intent": intent_id}
        if payload.amount:
            refund_params["amount"] = payload.amount

        refund = stripe.Refund.create(**refund_params)
        return RefundResponse(
            id=refund.id,
            status=refund.status,
            amount=refund.amount,
            currency=refund.currency,
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during refund: {e}")
        raise HTTPException(status_code=502, detail="Payment provider error")

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events.

    For the purpose of this demo we log the event and, when a payment is
    successful, we could update order status in a real database.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify signature if secret is configured
    if stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload, sig_header=sig_header, secret=stripe_webhook_secret
            )
        except ValueError as e:
            # Invalid payload
            logger.error(f"Invalid payload for Stripe webhook: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f"Invalid Stripe webhook signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # If no secret is set, we trust the payload (not recommended for prod)
        event = json.loads(payload)

    # Process relevant event types
    event_type = event["type"] if isinstance(event, dict) else event.type
    logger.info(f"Received Stripe event: {event_type}")

    if event_type == "checkout.session.completed":
        session = event["data"]["object"] if isinstance(event, dict) else event.data.object
        booking_id = session.get("metadata", {}).get("booking_id")
        logger.info(f"Checkout session completed for booking {booking_id}. Session ID: {session.get('id')}")
        # Here you would mark the booking as paid/confirmed in your DB.
    elif event_type == "payment_intent.succeeded":
        intent = event["data"]["object"] if isinstance(event, dict) else event.data.object
        booking_id = intent.get("metadata", {}).get("booking_id")
        logger.info(f"PaymentIntent succeeded for booking {booking_id}. Intent ID: {intent.get('id')}")
        # Update order status accordingly.
    else:
        logger.debug(f"Unhandled Stripe event type: {event_type}")

    return JSONResponse(content={"status": "success"})
