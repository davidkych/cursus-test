import {
  mdiAccountCircle,
  mdiMonitor,
  mdiSquareEditOutline,
  mdiTable,
  mdiTelevisionGuide,
  mdiViewList,
} from '@mdi/js'

/**
 * Public-mode sidebar menu
 * — every route is now prefixed with /public/*
 */
export default [
  {
    to: '/public/dashboard',
    icon: mdiMonitor,
    label: 'Dashboard',
  },
  {
    to: '/public/tables',
    icon: mdiTable,
    label: 'Tables',
  },
  {
    to: '/public/forms',
    icon: mdiSquareEditOutline,
    label: 'Forms',
  },
  {
    to: '/public/ui',
    icon: mdiTelevisionGuide,
    label: 'UI',
  },
  {
    to: '/public/profile',
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
