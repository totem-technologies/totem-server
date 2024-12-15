# import asyncio
# from io import BytesIO

# from PIL import Image
# from playwright.async_api import async_playwright


# class ScreenshotRequestBody:
#     def __init__(self, url: str, selector: str):
#         self.url = url
#         self.selector = selector


# async def take_screenshot(request_body: ScreenshotRequestBody):
#     if not request_body.url or not request_body.selector:
#         raise Exception("Missing required fields: url or selector")

#     browser = None
#     page = None

#     try:
#         async with async_playwright() as p:
#             browser = await p.chromium.launch()
#             page = await browser.new_page(device_scale_factor=2)

#             await page.set_viewport_size({"width": 1280, "height": 800})
#             await page.goto(request_body.url, wait_until="networkidle")

#             element = await page.query_selector(request_body.selector)
#             if not element:
#                 raise Exception("Element not found")

#             screenshot_buffer = await element.screenshot(type="png")
#             image = Image.open(BytesIO(screenshot_buffer))
#             with BytesIO() as output_buffer:
#                 image.save(output_buffer, format="WEBP", quality=80)
#                 optimized_image_buffer = output_buffer.getvalue()

#             return optimized_image_buffer

#     finally:
#         if page:
#             await page.close()
#         if browser:
#             await browser.close()


# async def main():
#     try:
#         request_body = ScreenshotRequestBody(
#             url="https://www.totem.org/circles/event/zdx624ofr/social",
#             selector="[data-img]",
#         )
#         screenshot = await take_screenshot(request_body)
#         with open("screenshot.webp", "wb") as f:
#             f.write(screenshot)
#         print("Screenshot saved as screenshot.webp")
#     except Exception as e:
#         print("Error:", str(e))


# if __name__ == "__main__":
#     asyncio.run(main())
