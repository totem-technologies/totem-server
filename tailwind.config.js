/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */

const basedir = "totem"

// Creme
// CMYK: 3, 3, 7, 0 RGB: 243, 241, 233 HEX: F3F1E9
// Yellow
// CMYK: 3, 11, 56, 0 RGB: 244, 220, 146 HEX: F4DC92
// Mauve
// CMYK: 41, 58, 9, 0 RGB: 152, 122, 165 HEX: 987AA5
// Slate
// CMYK: 81, 67, 56, 57 RGB: 38, 47, 55 HEX: 262F37
// Deep gray
// CMYK: 63, 57, 58, 36 RGB: 81, 79, 77
// HEX: 514F4D
// Blue
// CMYK: 41, 12, 4, 0 RGB: 155, 192, 221 HEX: 9BC0DD
// Blue tint
// CMYK: 75, 45, 30, 5 RGB: 85, 119, 143 HEX: 55778F
// Pink
// CMYK: 7, 49, 15, 0 RGB: 217, 153, 170 HEX: D999AA
// Pink tint
// CMYK: 38, 77, 45, 14 RGB: 139, 83, 99 HEX: 8B5363
const totemColors = {
  creme: "#F3F1E9",
  yellow: "#F4DC92",
  mauve: "#987AA5",
  slate: "#262F37",
  deepGray: "#514F4D",
  blue: "#9BC0DD",
  blueTint: "#55778F",
  pink: "#D999AA",
  pinkTint: "#8B5363",
}

module.exports = {
  content: [
    /**
     * HTML. Paths to Django template files that will contain Tailwind CSS classes.
     */

    /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
    `${basedir}/templates/**/*.html`,

    /*
     * Main templates directory of the project (BASE_DIR/templates).
     * Adjust the following line to match your project structure.
     */
    "./*/templates/**/*.html",

    /*
     * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
     * Adjust the following line to match your project structure.
     */
    `${basedir}/**/templates/**/*.html`,

    // Javascript files
    "./assets/js/**/*.js",

    // '../../**/*.py'
  ],
  theme: {
    extend: {
      colors: {
        tcreme: totemColors.creme,
        tyellow: totemColors.yellow,
        tmauve: totemColors.mauve,
        tslate: totemColors.slate,
        tdeepgray: totemColors.deepGray,
        tblue: totemColors.blue,
        tblueTint: totemColors.blueTint,
        tpink: totemColors.pink,
        tpinkTint: totemColors.pinkTint,
      },
      backgroundColor: {
        primary: totemColors.creme,
        tcreme: totemColors.creme,
        tyellow: totemColors.yellow,
        tmauve: totemColors.mauve,
        tslate: totemColors.slate,
      },
      fontFamily: {
        serif: ["Erode", "serif"],
        sans: ["Montserrat", "sans-serif"],
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    require("@tailwindcss/line-clamp"),
    require("@tailwindcss/aspect-ratio"),
    require("daisyui"),
  ],
  daisyui: {
    themes: [
      {
        mytheme: {
          ...require("daisyui/src/theming/themes").bumblebee,
          primary: totemColors.mauve,
        },
      },
    ], // true: all themes | false: only light + dark | array: specific themes like this ["light", "dark", "cupcake"]
    base: false, // applies background color and foreground color for root element by default
    styled: true, // include daisyUI colors and design decisions for all components
    utils: true, // adds responsive and modifier utility classes
    prefix: "", // prefix for daisyUI classnames (components, modifiers and responsive class names. Not colors)
    logs: false, // Shows info about daisyUI version and used config in the console when building your CSS
  },
}
