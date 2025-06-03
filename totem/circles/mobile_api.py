from ninja import Router
from django.http import HttpRequest

spaces_router = Router()


@spaces_router.post("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_subscribe")
def subscribe_to_space(request: HttpRequest, space_slug: str):
    return True


@spaces_router.delete("/subscribe/{space_slug}", response={200: bool}, url_name="spaces_unsubscribe")
def unsubscribe_to_space(request: HttpRequest, space_slug: str):
    return True


@spaces_router.get("/subscribe", response={200: bool}, url_name="spaces_subscriptions")
def list_subscriptions(request: HttpRequest):
    return True
