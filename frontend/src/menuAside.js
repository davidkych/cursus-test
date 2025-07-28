import {
  mdiAccountCircle,
  mdiMonitor,
  mdiSquareEditOutline,
  mdiTable,
  mdiTelevisionGuide,
  mdiViewList,
} from '@mdi/js'

/**
 * Main (non-admin) sidebar menu
 * — keep ONLY the items requested
 */
export default [
  {
    to: '/dashboard',
    icon: mdiMonitor,
    label: 'Dashboard',
  },
  {
    to: '/tables',
    icon: mdiTable,
    label: 'Tables',
  },
  {
    to: '/forms',
    icon: mdiSquareEditOutline,
    label: 'Forms',
  },
  {
    to: '/ui',
    icon: mdiTelevisionGuide,
    label: 'UI',
  },
  {
    to: '/profile',
    icon: mdiAccountCircle,
    label: 'Profile',
  },
  {
    label: 'Dropdown',
    icon: mdiViewList,
    menu: [
      { label: 'Item One' },
      { label: 'Item Two' },
    ],
  },
]
