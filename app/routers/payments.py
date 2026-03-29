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

        # Store intent details for later reference (e.g., in webhook handling)
        _payment_intent_store[intent.id] = {
            "user_email": current_user.email,
            "booking_id": payload.booking_id,
            "amount": payload.amount,
            "currency": payload.currency,
            "metadata": metadata,
        }

        return PaymentIntentResponse(client_secret=intent.client_secret)
    except Exception as exc:
        logger.exception("Failed to create payment intent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Create a Stripe Checkout Session and return the redirect URL."""
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

        # Store session details for later reference
        _checkout_session_store[session.id] = {
            "user_email": current_user.email,
            "booking_id": payload.booking_id,
            "amount": payload.amount,
            "currency": payload.currency,
            "metadata": metadata,
        }

        return CheckoutSessionResponse(url=session.url)
    except Exception as exc:
        logger.exception("Failed to create checkout session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/refund", response_model=RefundResponse)
async def refund_payment(
    payload: RefundRequest,
    current_user: User = Depends(role_required("customer")),
):
    """Refund a payment either by PaymentIntent ID or Checkout Session ID."""
    # Determine which identifier is provided
    if not payload.payment_intent_id and not payload.checkout_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either payment_intent_id or checkout_session_id must be provided.",
        )

    # Resolve PaymentIntent ID if a Checkout Session ID is supplied
    payment_intent_id = payload.payment_intent_id
    if payload.checkout_session_id:
        session = _checkout_session_store.get(payload.checkout_session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checkout session not found.",
            )
        # Verify ownership
        if session["user_email"] != current_user.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to refund this payment.",
            )
        # Retrieve the PaymentIntent linked to the session
        try:
            checkout_session = stripe.checkout.Session.retrieve(payload.checkout_session_id)
            payment_intent_id = checkout_session.payment_intent
        except Exception as exc:
            logger.exception("Failed to retrieve checkout session")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )
    else:
        # Verify ownership for direct PaymentIntent refunds
        intent_record = _payment_intent_store.get(payment_intent_id)
        if not intent_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment intent not found.",
            )
        if intent_record["user_email"] != current_user.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to refund this payment.",
            )

    # Perform the refund via Stripe
    try:
        refund_params: Dict[str, Any] = {"payment_intent": payment_intent_id}
        if payload.amount:
            refund_params["amount"] = payload.amount
        refund = stripe.Refund.create(**refund_params)

        return RefundResponse(
            id=refund.id,
            status=refund.status,
            amount=refund.amount,
            currency=refund.currency,
        )
    except Exception as exc:
        logger.exception("Refund failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events securely."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not stripe_webhook_secret:
        # If no secret is configured, we cannot verify signatures – reject for safety
        logger.warning("Stripe webhook secret not configured; rejecting webhook.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook secret not configured.",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    try:
        if event.type == "payment_intent.succeeded":
            intent = event.data.object  # type: ignore
            logger.info(f"PaymentIntent succeeded: {intent.id}")
            # Example: you could update booking status here using intent.metadata.get('booking_id')
        elif event.type == "checkout.session.completed":
            session = event.data.object  # type: ignore
            logger.info(f"Checkout session completed: {session.id}")
            # Example: update booking using session.metadata.get('booking_id')
        elif event.type == "charge.refunded":
            charge = event.data.object  # type: ignore
            logger.info(f"Charge refunded: {charge.id}")
        else:
            logger.info(f"Unhandled event type: {event.type}")
    except Exception as exc:
        logger.exception("Error processing webhook event")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    # Return a 200 response to acknowledge receipt of the event
    return JSONResponse(content={"status": "success"})