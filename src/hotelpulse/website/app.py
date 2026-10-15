"""Demo hotel website with a working booking flow and the HotelPulse tracker.

Run with ``uvicorn --factory hotelpulse.website.app:create_app``. Pages are rendered on the
server; each page declares the analytics events it fires on load (``page.events``), clicks
use ``data-track`` attributes. Pay with card 4000 0000 0000 0002 to see a declined payment.
"""

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hotelpulse import settings
from hotelpulse.website import engine

HERE = Path(__file__).parent
COUNTRIES = {
    "PRT": "Portugal", "GBR": "United Kingdom", "DEU": "Germany", "FRA": "France",
    "ESP": "Spain", "ITA": "Italy", "NLD": "Netherlands", "USA": "United States",
    "CHN": "China", "BRA": "Brazil",
}  # fmt: skip
HOTEL_COPY = {
    "CITY": "Steps from Avenida da Liberdade - rooftop bar, river views, metro at the door.",
    "RESORT": "Cliff-top resort above the Albufeira beaches - three pools, spa, kids club.",
}


def create_app() -> FastAPI:
    app = FastAPI(title="HotelPulse Hotels", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    dsn = settings.pms_admin_dsn()
    collector_url = os.environ.get("COLLECTOR_PUBLIC_URL", "http://localhost:8010").rstrip("/")
    cache: dict[str, Any] = {}

    def connect() -> psycopg.Connection:
        return psycopg.connect(dsn)

    def reference(conn: psycopg.Connection) -> tuple[dict[str, engine.Hotel], dict]:
        if "hotels" not in cache:
            cache["hotels"] = engine.load_hotels(conn)
            cache["prices"] = engine.load_price_table(conn)
        return cache["hotels"], cache["prices"]

    def render(request: Request, name: str, status: int = 200, **context: Any) -> HTMLResponse:
        context.setdefault("page", {"type": "other", "events": []})
        return templates.TemplateResponse(
            request, name, {"collector_url": collector_url, **context}, status_code=status
        )

    def stay_params(stay: engine.Stay) -> dict[str, Any]:
        return {
            "hotel": stay.hotel.code,
            "checkin": stay.checkin.isoformat(),
            "checkout": stay.checkout.isoformat(),
            "adults": stay.adults,
            "children": stay.children,
        }

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, error: str | None = None) -> HTMLResponse:
        with connect() as conn:
            hotels, _ = reference(conn)
        checkin = date.today() + timedelta(days=21)
        return render(
            request,
            "index.html",
            hotels=list(hotels.values()),
            copy=HOTEL_COPY,
            checkin=checkin,
            checkout=checkin + timedelta(days=3),
            error=error,
            page={"type": "home", "events": []},
        )

    @app.get("/rooms", response_class=HTMLResponse)
    def rooms(
        request: Request,
        hotel: str,
        checkin: date,
        checkout: date,
        adults: int = 2,
        children: int = 0,
    ) -> Response:
        with connect() as conn:
            hotels, prices = reference(conn)
            try:
                stay = engine.validate_stay(hotels, hotel, checkin, checkout, adults, children)
            except engine.InvalidStay as exc:
                return RedirectResponse(f"/?error={exc}", status_code=303)
            offers = engine.room_offers(conn, prices, stay)
            left = engine.rooms_left(conn, stay)
        search = {**stay_params(stay), "hotel_code": stay.hotel.code, "nights": stay.nights}
        del search["hotel"]
        return render(
            request,
            "rooms.html",
            stay=stay,
            params=stay_params(stay),
            offers=offers if left else [],
            rooms_left=left,
            page={
                "type": "rooms",
                "events": [{"name": "search_availability", "properties": search}],
            },
        )

    def checkout_context(
        stay: engine.Stay, offer: engine.RoomOffer, params: dict, error: str | None
    ) -> dict:
        value = float(offer.total)
        events = []
        if error:
            events.append(
                {
                    "name": "payment_failed",
                    "properties": {
                        "error_code": "card_declined",
                        "value": value,
                        "currency": "EUR",
                    },
                }
            )
        else:
            events.append(
                {
                    "name": "begin_checkout",
                    "properties": {
                        "hotel_code": stay.hotel.code,
                        "room_type_code": offer.code,
                        "value": value,
                        "currency": "EUR",
                    },
                }
            )
        return {
            "stay": stay,
            "offer": offer,
            "params": params,
            "breakfast_total": engine.breakfast_total(stay),
            "countries": COUNTRIES,
            "error": error,
            "page": {"type": "checkout", "events": events},
        }

    def find_offer(conn, prices, stay: engine.Stay, room: str) -> engine.RoomOffer | None:
        return next((o for o in engine.room_offers(conn, prices, stay) if o.code == room), None)

    @app.get("/checkout", response_class=HTMLResponse)
    def checkout(
        request: Request,
        hotel: str,
        room: str,
        checkin: date,
        checkout: date,
        adults: int = 2,
        children: int = 0,
    ) -> Response:
        with connect() as conn:
            hotels, prices = reference(conn)
            try:
                stay = engine.validate_stay(hotels, hotel, checkin, checkout, adults, children)
            except engine.InvalidStay as exc:
                return RedirectResponse(f"/?error={exc}", status_code=303)
            offer = find_offer(conn, prices, stay, room)
        if offer is None:
            return RedirectResponse("/?error=That room is no longer available.", status_code=303)
        params = {**stay_params(stay), "room": offer.code}
        return render(request, "checkout.html", **checkout_context(stay, offer, params, None))

    @app.post("/book", response_class=HTMLResponse)
    def book(
        request: Request,
        hotel: Annotated[str, Form()],
        room: Annotated[str, Form()],
        checkin: Annotated[date, Form()],
        checkout: Annotated[date, Form()],
        adults: Annotated[int, Form()],
        children: Annotated[int, Form()],
        first_name: Annotated[str, Form(max_length=80)],
        last_name: Annotated[str, Form(max_length=80)],
        email: Annotated[str, Form(max_length=200)],
        country: Annotated[str, Form()],
        card_number: Annotated[str, Form()],
        breakfast: Annotated[bool, Form()] = False,
    ) -> Response:
        with connect() as conn:
            hotels, prices = reference(conn)
            try:
                stay = engine.validate_stay(hotels, hotel, checkin, checkout, adults, children)
            except engine.InvalidStay as exc:
                return RedirectResponse(f"/?error={exc}", status_code=303)
            offer = find_offer(conn, prices, stay, room)
            if offer is None:
                return RedirectResponse("/?error=That room is no longer available.", 303)
            params = {**stay_params(stay), "room": offer.code}
            if "".join(card_number.split()) == engine.TEST_DECLINED_CARD:
                context = checkout_context(stay, offer, params, "Your card was declined.")
                return render(request, "checkout.html", status=402, **context)
            code = engine.create_booking(
                conn,
                stay,
                offer,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                email=email.strip(),
                country_code=country if country in COUNTRIES else None,
                breakfast=breakfast,
            )
        # ?new=1 marks the first view; the page strips it so a reload does not re-send
        # booking_confirmed (a classic cause of double-counted conversions)
        return RedirectResponse(f"/confirmation/{code}?new=1", status_code=303)

    @app.get("/confirmation/{code}", response_class=HTMLResponse)
    def confirmation(request: Request, code: str, new: int = 0) -> Response:
        with connect() as conn:
            booking = engine.find_booking(conn, code)
        if booking is None:
            return RedirectResponse("/?error=Booking not found.", status_code=303)
        events = []
        if new:
            events.append(
                {
                    "name": "booking_confirmed",
                    "properties": {
                        "confirmation_code": booking["confirmation_code"],
                        "hotel_code": booking["hotel_code"],
                        "room_type_code": booking["room_type_code"],
                        "checkin": booking["checkin"].isoformat(),
                        "checkout": booking["checkout"].isoformat(),
                        "value": float(booking["room_total"]),
                        "currency": "EUR",
                    },
                }
            )
        return render(
            request,
            "confirmation.html",
            booking=booking,
            page={"type": "confirmation", "events": events},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
