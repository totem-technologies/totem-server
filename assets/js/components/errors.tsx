import { ErrorBoundary } from "solid-js"

function InstrumentedErrorBoundary(props: { children: any }) {
  return (
    <ErrorBoundary
      fallback={(error, reset) => {
        ;(globalThis as any).Sentry?.captureException(error)
        return (
          <div>
            <h3 class="pb-5" onclick={reset}>
              Something went wrong. Please refresh this page, or try again
              later. This error has been sent to our team.
            </h3>
            <pre>Error: {error.message}</pre>
          </div>
        )
      }}>
      {props.children}
    </ErrorBoundary>
  )
}

export default InstrumentedErrorBoundary
