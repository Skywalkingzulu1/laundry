import os
import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, PositiveInt

router = APIRouter()

# Load Stripe secret key from environment; fallback to a placeholder for local testing
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_123")

class CreatePaymentIntentRequest(BaseModel):
    amount: PositiveInt  # amount in the smallest currency unit (e.g., cents)
    currency: str = "usd"
    metadata: dict = {}

@router.post("/create-payment-intent")
async def create_payment_intent(payload: CreatePaymentIntentRequest):
    """
    Create a Stripe PaymentIntent and return its client_secret so the frontend can
    complete the payment securely.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=payload.amount,
            currency=payload.currency,
            metadata=payload.metadata,
        )
        return {"client_secret": intent.client_secret}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint to receive asynchronous events such as payment confirmation.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret or not sig_header:
        raise HTTPException(status_code=400, detail="Missing webhook secret or signature header")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    # Example handling of a successful payment intent
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        # TODO: Update order status in your database, send confirmation email, etc.
        print(f"✅ PaymentIntent succeeded: {payment_intent['id']}")

    # Respond to Stripe to acknowledge receipt
    return {"status": "received"}