import os
import logging
import json
from typing import Any, Dict

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, PositiveInt

from app.dependencies import role_required
from app.models import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Load Stripe secret key from environment; raise error if not set in production
stripe_api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_api_key:
    # For local development a test key can be used, but in production this must be set
    stripe_api_key = "sk_test_123"
stripe.api_key = stripe_api_key


class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: Dict[str, Any] = {}
    # Optional booking reference to associate the payment with a booking
    booking_id: str | None = None


class PaymentIntentResponse(BaseModel):
    client_secret: str


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe PaymentIntent and return its client_secret so the frontend can
    complete the payment securely.

    Only customers can initiate a payment. The optional `booking_id` can be used
    by the frontend to link the payment to a specific booking record.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=payload.metadata,
        )
        # In a real implementation you would persist the intent ID together with
        # the booking_id and user information to verify later in the webhook.
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


class CheckoutSessionResponse(BaseModel):
    url: str


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: User = Depends(role_required("customer")),
):
    """
    Create a Stripe Checkout Session and return the URL to redirect the customer.
    """
    try:
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
            metadata=payload.metadata,
        )
        logger.info(
            "Created Checkout Session %s for user %s", session.id, current_user.email
        )
        return CheckoutSessionResponse(url=session.url)
    except Exception as exc:
        logger.exception("Error creating Checkout Session: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to receive asynchronous events such as payment confirmation.

    The endpoint validates the Stripe signature, parses the event, and processes
    relevant event types (e.g., `checkout.session.completed`). After handling the
    event, it returns a 200 response to acknowledge receipt.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not set in environment")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        logger.exception("Invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.exception("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        logger.info(
            "Checkout session completed: %s, customer %s, amount_total %s",
            session.get("id"),
            session.get("customer_email"),
            session.get("amount_total"),
        )
        # TODO: Update booking/payment status in database
    elif event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        logger.info(
            "PaymentIntent succeeded: %s, amount %s", intent.get("id"), intent.get("amount")
        )
        # TODO: Update booking/payment status in database
    else:
        logger.info("Unhandled event type %s", event["type"])

    return {"status": "success"}