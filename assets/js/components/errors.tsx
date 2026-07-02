import { ErrorBoundary, type JSXElement } from "solid-js"

function InstrumentedErrorBoundary(props: { children: JSXElement }) {
  return (
    <ErrorBoundary
      fallback={(error, reset) => {
        console.log("ErrorBoundary fallback", error)
        ;(globalThis as any).Sentry?.captureException(error)
        return (
          <div>
            <h3 class="pb-5" onClick={reset} onKeyUp={reset}>
              Something went wrong. Please refresh this page, or try again
              later. This error has been sent to our team.
            </h3>
            <pre>Error: {error}</pre>
          </div>
        )
      }}>
      {props.children}
    </ErrorBoundary>
  )
}

export default InstrumentedErrorBoundary
