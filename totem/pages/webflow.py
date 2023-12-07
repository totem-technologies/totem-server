import lxml.html
import requests

requests_session = requests.Session()


def get_webflow_page(page):
    # proxy webflow pages from remote server
    # Send a GET request to the Webflow page
    if page is None:
        response = requests_session.get("https://vanessas-top-notch-site-fc65f5.webflow.io/")
    else:
        response = requests_session.get(f"https://vanessas-top-notch-site-fc65f5.webflow.io/{page}")
    # Return the content of the Webflow page as a response
    return _parse_page(response.content.decode("utf-8"))


def _parse_page(content: str) -> str:
    # Find the start and end of the content
    parser = lxml.html.HTMLParser(encoding="utf-8")
    doc = lxml.html.fromstring(content, parser=parser)
    # Find the start and end of the content
    els = doc.cssselect("body")
    scripts = doc.cssselect("head script")
    css = doc.cssselect("head style")
    links = doc.cssselect("head link[type='text/css']")
    # Return the content between the start and end
    if els:
        content = ""
        for el in scripts:
            content += str(lxml.html.tostring(el, encoding="unicode"))
        for el in css:
            content += str(lxml.html.tostring(el, encoding="unicode"))
        for el in links:
            content += str(lxml.html.tostring(el, encoding="unicode"))

        for el in els[0].iterchildren():
            content += str(lxml.html.tostring(el, encoding="unicode"))

        return content
    else:
        return ""
