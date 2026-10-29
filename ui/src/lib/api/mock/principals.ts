import type { Principal } from '../types';

export const SCHEDULER: Principal = { kind: 'scheduler', name: 'scheduler', displayName: 'Scheduler' };
export const SENSOR_DAEMON: Principal = { kind: 'sensor', name: 'sensors', displayName: 'Sensor daemon' };
export const CI_ACCOUNT: Principal = { kind: 'service_account', name: 'svc-ci', displayName: 'CI service account' };
export const DEMO_USER: Principal = { kind: 'user', name: 'demo', displayName: 'Demo User' };
export const OPS_USER: Principal = { kind: 'user', name: 'ops-oncall', displayName: 'On-call Operator' };
