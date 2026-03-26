from fastapi import FastAPI
from app.routers import users, bookings, payments

app = FastAPI(title="LaundryPool API")

app.include_router(users.router, prefix="/auth", tags=["auth"])
app.include_router(bookings.router, prefix="/booking", tags=["booking"])
app.include_router(payments.router, prefix="/payment", tags=["payment"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}