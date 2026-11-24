from totem.api.api import mobile_api


def test_mobile_openapi_contract() -> None:
    schema = mobile_api.get_openapi_schema()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    register = paths["/api/mobile/protected/fcm/register"]["post"]
    request_ref = register["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert register["operationId"].endswith("register_fcm_fid")
    assert request_ref == "#/components/schemas/FCMFIDRegisterSchema"
    assert components["FCMFIDRegisterSchema"]["required"] == ["fid"]
    assert set(components["FCMFIDRegisterSchema"]["properties"]) == {"fid"}
    assert (
        register["responses"][201]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/FCMFIDResponseSchema"
    )

    unregister = paths["/api/mobile/protected/fcm/unregister/{fid}"]["delete"]
    assert unregister["operationId"].endswith("unregister_fcm_fid")

    payload = components["SessionNotificationPayload"]
    assert {"type", "space_slug", "session_slug"} <= set(payload["required"])
    assert payload["properties"]["type"]["$ref"] == "#/components/schemas/NotificationType"
    assert set(components["NotificationType"]["enum"]) == {
        "session_starting",
        "session_advertisement",
        "missed_session",
    }
