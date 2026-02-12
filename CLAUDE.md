This is the API and Website for totem.org, a nonprofit that provides moderated support groups on various topics. There is also a Flutter app that uses the /mobile/ api endpoints, which is not in this codebase.

It's a standard Django app that runs in a Docker container in production and in development. It uses Postgres for the database. All the common management commands are located in the Makefile at the root, look there before trying to run any commands. For example, don't run pytest directly (this will fail, tests need to run in Docker), use `make test` to run all tests.

Django development notes:

- Use function-based views, no class views, unless it significantly simplifies the code.
  - For reasoning and examples you can review https://spookylukey.github.io/django-views-the-right-way/index.html
- Always have Django generate migrations. You can edit the migration later if needed.
- Use Python type annotations and try to structure code so that types are effective

Javascript notes:

The front end code is in the /assets folder. The front end uses a generated OpenAPI schema (from Django Ninja) to render mini apps (via custom elements) on various MPA-style pages.

Use tailwind, SolidJS, and TypeScript.

General engineering practices:

- For new features and especially bug fixes, follow Test Driven Development practices. Always make at least one failing test first before changing the functional code. If the test(s) require heavy mocking, think about how the code can be refactored or testing at a different level of abstraction.
- Always use type annotations. If typing is verbose, complicated or getting in the way, take a step back and reflect if a different implementation is needed. The goal is to catch as many bugs as possible via static analysis, then via test code. Bugs found in production are a major engineering failure.
- Strive to make the most of the application and third-party code we have integrated. The best solution is usually the one that requires the least amount of code to do. This is not a pass to be lazy, in fact, simple is hard and may require thinking more deeply about what needs to be done. Make sure you research on the internet when changes seem complicated. It's very likely problems we have in this codebase have been solved before.
- Conversely, every 3rd party library we integrate is technical debt. Only add new libraries if they add significant value and we're likely to use a majority of it. Before adding a dependency, you should see how the library solves the problem and decide if we should just adapt the code to our specific needs.

Brand colors: cream #f3f1e9, slate #262f37, mauve #987aa5, yellow #f4dc92, pink #d999aa

Font: Montserrat
