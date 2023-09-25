export default function Button(props) {
  var colors = {
    blue: "bg-blue-500 hover:bg-blue-700",
    red: "bg-red-500 hover:bg-red-700",
    green: "bg-green-500 hover:bg-green-700",
  }
  var color = colors[props.color] || colors.green
  return <button class={`btn-primary ${color}`}>{props.children}</button>
}
