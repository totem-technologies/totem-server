from pydantic import BaseModel, HttpUrl


class EmailTemplate(BaseModel):
    template: str
    subject: str
    support_email: str = "bo@totem.org"

    def get_html_template(self):
        return f"{self.template}.html"

    def get_text_template(self):
        return f"{self.template}.txt"

    def render_html(self):
        return f"render_html {self} {self.get_html_template()} {self.model_dump()}"

    def render_text(self):
        return f"render_text {self} {self.get_text_template()} {self.model_dump()}"


class Email(BaseModel):
    recipient: str

    def get_template(self) -> EmailTemplate:
        raise NotImplementedError


class ButtonEmailTemplate(EmailTemplate):
    template: str = "button"
    button_text: str
    link: HttpUrl
    title: str


class LoginEmail(Email):
    url: HttpUrl
    button_text: str = "Sign in"
    subject: str = "Totem sign in link"
    title: str = "Sign in link"

    def get_template(self):
        return ButtonEmailTemplate(
            button_text=self.button_text,
            link=self.url,
            title=self.title,
            subject=self.subject,
        )


def send_login_email(recipient: str, url: str):
    email = LoginEmail(
        recipient="bo@totem.org",
        url="https://totem.org",  # type: ignore
    )
    tpl = email.get_template()
    print(tpl.render_html())
    print(tpl.render_text())
    send_template_email(tpl, email.recipient)


def main():
    send_login_email("bo@totem.org", "https://totem.org")


def send_template_email(template: EmailTemplate, recipient: str):
    send_email(
        subject=template.subject,
        html_message=template.render_html(),
        text_message=template.render_text(),
        recipient_list=[recipient],
    )


def send_email(subject: str, html_message: str, text_message: str, recipient_list: list[str]):
    print("send_email")


if __name__ == "__main__":
    main()
