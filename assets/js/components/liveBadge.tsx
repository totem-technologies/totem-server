// The one "this session is live" pill, shared by the dashboard countdown
// and the session lists so copy and styling can't drift.
export default function LiveBadge(props: { small?: boolean }) {
  return (
    <span
      class={`bg-tyellow text-tslate inline-flex items-center gap-2 rounded-full font-bold whitespace-nowrap ${
        props.small ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm"
      }`}>
      <span class="relative flex h-2 w-2">
        <span class="bg-tslate absolute inline-flex h-full w-full animate-ping rounded-full opacity-40" />
        <span class="bg-tslate relative inline-flex h-2 w-2 rounded-full" />
      </span>
      Happening now
    </span>
  )
}
