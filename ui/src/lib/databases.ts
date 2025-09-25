/**
 * Database configuration for PMM Companion UI
 */

export const databases = [
  { 
    value: '.data/pmm.db', 
    label: 'Live PMM Database',
    description: 'Current active PMM session data'
  },
];

export const defaultDatabase = databases[0].value;

export default databases;
