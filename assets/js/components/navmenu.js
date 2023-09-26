import { useEffect, useState } from "preact/hooks"
import Dropdown from "./dropdown"
function NavMenu(props) {
  ;[links, setLinks] = useState([])
  useEffect(() => {
    links = JSON.parse(document.getElementById(props.dataid).textContent)
    setLinks(links)
  }, [])

  const button = (
    <button class="flex items-center gap-1 pr-3">
      Menu
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="h-5 w-5 text-gray-400"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fill-rule="evenodd"
          d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
          clip-rule="evenodd"
        />
      </svg>
    </button>
  )
  const menu = (
    <div class="mt-2 w-40 rounded-md bg-white shadow-md">
      {links.map((link) => (
        <a
          class="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm first-of-type:rounded-t-md last-of-type:rounded-b-md hover:bg-gray-50 disabled:text-gray-500"
          href={link.href}
        >
          {link.title}
        </a>
      ))}
    </div>
  )
  return (
    <>
      <div class="hidden md:block">
        {links.map((link) => (
          <a class="pr-5 hover:text-tblue" href={link.href}>
            {link.title}
          </a>
        ))}
      </div>
      <div class="md:hidden ">
        <Dropdown button={button} menu={menu}></Dropdown>
      </div>
    </>
  )
}

NavMenu.tagName = "t-navmenu"

export default NavMenu
