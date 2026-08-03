export type RoleKey =
  | 'admin'
  | 'ceo'
  | 'truong_kd'
  | 'sales1'
  | 'sales2'
  | 'ky_thuat'
  | 'ke_toan';

export interface RoleAccount {
  key: RoleKey;
  label: string;
  login: string;
  password: string;
  /** File lưu storageState sau khi login, dùng lại cho các spec cùng role */
  storageStatePath: string;
}

const PASSWORD = 'Demo@2026';

export const ROLES: Record<RoleKey, RoleAccount> = {
  admin: {
    key: 'admin',
    label: 'Admin/IT',
    login: 'admin@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/admin.json',
  },
  ceo: {
    key: 'ceo',
    label: 'CEO',
    login: 'ceo@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/ceo.json',
  },
  truong_kd: {
    key: 'truong_kd',
    label: 'Trưởng phòng Kinh doanh',
    login: 'truongkd@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/truong_kd.json',
  },
  sales1: {
    key: 'sales1',
    label: 'BA/Sales #1',
    login: 'sales1@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/sales1.json',
  },
  sales2: {
    key: 'sales2',
    label: 'BA/Sales #2 (test cảnh báo gộp đơn)',
    login: 'sales2@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/sales2.json',
  },
  ky_thuat: {
    key: 'ky_thuat',
    label: 'Kỹ thuật',
    login: 'kythuat@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/ky_thuat.json',
  },
  ke_toan: {
    key: 'ke_toan',
    label: 'Kế toán nội bộ',
    login: 'ketoan@dlm.demo',
    password: PASSWORD,
    storageStatePath: 'tests/.auth/ke_toan.json',
  },
};
