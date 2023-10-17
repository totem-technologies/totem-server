from dataclasses import dataclass


@dataclass
class FAQ:
    question: str
    answer: str


faqs = [
    FAQ(
        question="Can I be anonymous?",
        answer="Yes! We don't mind if you don't use your real name. We will require \
                    enough information for moderation, like your email, but to other people \
                        in your Circles (including Keepers) you can be whoever you want to \
                            be. However, we do require you share authentic stories.",
    ),
    FAQ(
        question="What about privacy?",
        answer="We have zero tolerance about discussing what happens in Totem to the \
                    outside. Anyone doing this will be permanently removed. Additionally, we \
                        built Totem on top of HIPAA-compliant services, the same software \
                            that therapists and doctors use to do online sessions. Your \
                communications are encrypted. The only people who can hear your shares are the \
                    people in your Circle.",
    ),
    FAQ(
        question="Is this a replacement for therapy?",
        answer="No. While many people prefer Totem Circles to therapy, it is not a \
                replacement for traditional one-on-one therapy. However, Totem does make a great \
                supplement if you already have ongoing therapy sessions and can help create a \
                deeper understanding with your work there.",
    ),
    FAQ(
        question="Are Keepers therapists?",
        answer="Generally, no. Keepers are different from therapists in that they are \
                only present to keep the Circle running smoothly and safely for everyone. \
                Otherwise, Keepers are there to be involved with the discussion like everyone else \
                    and not to offer advice or guidance. There is no hierarchy in a Circle.",
    ),
    FAQ(
        question="How much does Totem cost?",
        answer="It depends on the Circle, some are free, some aren't. Our mission is to \
                    make Totem Circles accessible to as many people as possible. In the future we'll \
                        add the ability to donate directly to your Keeper if you'd like to \
                            support them. ",
    ),
]

quotes = [
    "I appreciate having a space to express myself and not feel the need to validate or \
                respond to others.",
    "It was the best experience.",
    "I'm so glad I came, this is exactly what I've been needing.",
    "This is definitely a safe and welcoming environment.",
    "My expectations were exceeded 10000%.",
    "YES!!! I love the safe space that was, created.",
]
