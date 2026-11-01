#!/usr/bin/env node
/*
 * Test identities for the API / security pillars.
 *
 * Creates (or removes) synthetic records with fixed `aaa…` ObjectIds so the
 * engine can mint JWTs for a BASIC tenant, a STANDARD tenant and a platform admin:
 *
 *   merchants     aaa000000000000000000020  BASIC-plan test company (entitlement-denial cases)
 *   employees     aaa000000000000000000021  ROLE ADMIN employee of that company
 *   useraccounts  aaa000000000000000000022  login account for that employee
 *   merchants     aaa000000000000000000001  STANDARD test company
 *   employees     aaa000000000000000000002  ROLE ADMIN employee of that company
 *   useraccounts  aaa000000000000000000003  login account for that employee
 *   merchants     aaa000000000000000000010  isPlatform:true company (only if none exists)
 *   users         aaa000000000000000000011  ROLE ADMIN platform user
 *
 * Usage (from the automation-testing repo root):
 *   node fixtures/test-identities.js            # dry run: shows what exists / would change
 *   node fixtures/test-identities.js --apply    # create the missing records (idempotent)
 *   node fixtures/test-identities.js --cleanup  # delete these records (keeps the platform company)
 *   node fixtures/test-identities.js --cleanup --include-platform  # also delete the aaa…010 platform company
 *
 * Only run this against a LOCAL / test database. It refuses non-localhost URIs
 * unless ALLOW_REMOTE_FIXTURES=1 is set.
 *
 * Settings come from the environment or the repo's .env file:
 *   MONGODB_URI        default mongodb://localhost:27017/topauto1653_ecommerce?replicaSet=rs0
 *   BACKEND_WORKSPACE  backend repo whose node_modules provide `mongodb` + `bcryptjs`
 *                      (default: ../topautokh-api next to this repo)
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { createRequire } = require('module');

const ENGINE_ROOT = path.resolve(__dirname, '..');

function loadDotEnv() {
  const file = process.env.AUTOMATION_ENV_FILE
    ? path.resolve(ENGINE_ROOT, process.env.AUTOMATION_ENV_FILE)
    : path.join(ENGINE_ROOT, '.env');
  if (!fs.existsSync(file)) return;
  for (let line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    line = line.trim().replace(/^export\s+/, '');
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    const val = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
    if (val && process.env[key] === undefined) process.env[key] = val;
  }
}

function resolveBackend() {
  const ws = process.env.WORKSPACE_ROOT
    ? path.resolve(ENGINE_ROOT, process.env.WORKSPACE_ROOT)
    : path.dirname(ENGINE_ROOT);
  const backend = process.env.BACKEND_WORKSPACE
    ? path.resolve(ws, process.env.BACKEND_WORKSPACE)
    : path.join(ws, 'topautokh-api');
  if (!fs.existsSync(path.join(backend, 'node_modules'))) {
    console.error(`[fixtures] ${backend}/node_modules not found. Install the backend deps or set BACKEND_WORKSPACE.`);
    process.exit(2);
  }
  return createRequire(path.join(backend, 'package.json'));
}

const IDS = {
  basicCompany: 'aaa000000000000000000020',
  basicEmployee: 'aaa000000000000000000021',
  basicAccount: 'aaa000000000000000000022',
  premiumCompany: 'aaa000000000000000000001',
  premiumEmployee: 'aaa000000000000000000002',
  premiumAccount: 'aaa000000000000000000003',
  platformCompany: 'aaa000000000000000000010',
  platformAdmin: 'aaa000000000000000000011',
};

async function main() {
  loadDotEnv();
  const mode = process.argv.includes('--cleanup') ? 'cleanup' : process.argv.includes('--apply') ? 'apply' : 'dry-run';
  const uri = process.env.MONGODB_URI || 'mongodb://localhost:27017/topauto1653_ecommerce?replicaSet=rs0';
  const authority = uri.replace(/^mongodb(\+srv)?:\/\//, '').split('/')[0];
  const host = authority.split('@').pop().split(',')[0].replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  if (!['localhost', '127.0.0.1', '::1'].includes(host) && process.env.ALLOW_REMOTE_FIXTURES !== '1') {
    console.error(`[fixtures] Refusing to touch non-local MongoDB host "${host}". Set ALLOW_REMOTE_FIXTURES=1 if this is a disposable test DB.`);
    process.exit(2);
  }

  const req = resolveBackend();
  const { MongoClient, ObjectId } = req('mongodb');
  const bcrypt = req('bcryptjs');
  const oid = (hex) => new ObjectId(hex);

  const client = new MongoClient(uri, { serverSelectionTimeoutMS: 5000, useUnifiedTopology: true });
  await client.connect();
  const db = client.db();
  console.log(`[fixtures] mode=${mode} db=${db.databaseName} host=${host}`);

  const col = (name) => db.collection(name);
  const existingPlatform = await col('merchants').findOne({ isPlatform: true }, { projection: { _id: 1, name: 1 } });
  const platformCompanyId = existingPlatform ? existingPlatform._id : oid(IDS.platformCompany);
  const now = new Date();
  // The engine's default BASIC tenant is the team dev DB's "Top Auto Default" company
  // (orchestration/config.py). When it exists, keep it: 10 API cases use its records.
  const teamDefaultCompany = await col('merchants').findOne({ _id: oid('6a4082e590497f6ad8587dc8') }, { projection: { _id: 1 } });

  // Status fields are ObjectId references to lookup rows that differ per database,
  // so resolve them from the target DB instead of hard-coding ids.
  const employeeStatusParent = await col('codedefinitions').findOne({ codeName: 'Employee Status' }, { projection: { _id: 1 } });
  const activeEmployeeStatus = employeeStatusParent
    ? await col('codedefinitions').findOne({ parentCodeId: String(employeeStatusParent._id), codeName: 'Active' }, { projection: { _id: 1 } })
    : null;
  const commonAccountStatus = (await col('useraccounts')
    .aggregate([{ $match: { status: { $ne: null } } }, { $group: { _id: '$status', n: { $sum: 1 } } }, { $sort: { n: -1 } }, { $limit: 1 }])
    .toArray())[0];
  const employeeStatus = activeEmployeeStatus ? activeEmployeeStatus._id : null;
  const accountStatus = commonAccountStatus ? commonAccountStatus._id : null;

  const tenantLimits = { maxBranches: 3, maxCars: 200, maxCustomers: 2000, maxStorageGb: 10, maxUsers: 20 };
  const records = [
    {
      col: 'merchants', _id: oid(IDS.basicCompany),
      doc: {
        name: 'Automation Test Basic Co', business: 'CAR_DEALERSHIP', businesses: ['CAR_DEALERSHIP'],
        subscriptionPackage: 'BASIC', isActive: true, status: 'Approved', lifecycleStatus: 'ACTIVE', isPlatform: false,
        contractStartDate: null, contractEndDate: null, ...tenantLimits, created: now, updated: now,
      },
    },
    {
      col: 'employees', _id: oid(IDS.basicEmployee),
      doc: {
        firstName: 'Automation', lastName: 'BasicAdmin', role: 'ROLE ADMIN', companyId: oid(IDS.basicCompany),
        status: employeeStatus, branchAccessMode: 'ALL', address: {}, avatar: '', imageUrl: '', nid: '', telegramUserName: '',
        created: now, updated: now,
      },
    },
    {
      col: 'useraccounts', _id: oid(IDS.basicAccount),
      doc: { refId: oid(IDS.basicEmployee), password: null, status: accountStatus },
    },
    {
      col: 'merchants', _id: oid(IDS.premiumCompany),
      doc: {
        name: 'Automation Test Standard Co', business: 'CAR_DEALERSHIP', businesses: ['CAR_DEALERSHIP'],
        subscriptionPackage: 'STANDARD', isActive: true, status: 'Approved', lifecycleStatus: 'ACTIVE', isPlatform: false,
        contractStartDate: null, contractEndDate: null, ...tenantLimits, created: now, updated: now,
      },
    },
    {
      col: 'employees', _id: oid(IDS.premiumEmployee),
      doc: {
        firstName: 'Automation', lastName: 'StandardAdmin', role: 'ROLE ADMIN', companyId: oid(IDS.premiumCompany),
        status: employeeStatus, branchAccessMode: 'ALL', address: {}, avatar: '', imageUrl: '', nid: '', telegramUserName: '',
        created: now, updated: now,
      },
    },
    {
      col: 'useraccounts', _id: oid(IDS.premiumAccount),
      doc: { refId: oid(IDS.premiumEmployee), password: null, status: accountStatus },
    },
    // The platform company is only created when the DB has no isPlatform merchant yet.
    ...(existingPlatform ? [] : [{
      col: 'merchants', _id: oid(IDS.platformCompany),
      doc: {
        name: 'Auto360', business: 'Platform Administration', subscriptionPackage: 'PREMIUM', isActive: true, status: 'Approved',
        lifecycleStatus: 'ACTIVE', isPlatform: true, contractStartDate: null, contractEndDate: null,
        maxBranches: null, maxCars: null, maxCustomers: null, maxStorageGb: null, maxUsers: null, created: now, updated: now,
      },
    }]),
    {
      col: 'users', _id: oid(IDS.platformAdmin),
      doc: {
        firstName: 'Automation', lastName: 'PlatformAdmin', role: 'ROLE ADMIN', companyId: platformCompanyId,
        status: true, statusCode: '01', created: now, updated: now,
      },
    },
  ];

  if (mode !== 'cleanup' && !employeeStatus) {
    console.warn('  warning: no codedefinitions "Employee Status" → "Active" row; the test employee will be rejected as inactive. Seed the code definitions first.');
  }

  if (mode === 'cleanup') {
    // The platform company may be the only isPlatform merchant the app has, so it
    // is kept unless --include-platform is passed.
    const includePlatform = process.argv.includes('--include-platform');
    const targets = records.filter((r) => String(r._id) !== IDS.platformCompany);
    if (includePlatform) targets.push({ col: 'merchants', _id: oid(IDS.platformCompany) });
    else console.log(`  kept     merchants ${IDS.platformCompany} (pass --include-platform to delete it too)`);
    for (const r of targets) {
      const res = await col(r.col).deleteOne({ _id: r._id });
      if (res.deletedCount) console.log(`  deleted ${r.col} ${r._id}`);
    }
    await client.close();
    console.log('[fixtures] cleanup done');
    return;
  }

  for (const r of records) {
    const found = await col(r.col).findOne({ _id: r._id }, { projection: { _id: 1 } });
    if (found) {
      console.log(`  exists   ${r.col} ${r._id}`);
      continue;
    }
    if (mode === 'dry-run') {
      console.log(`  missing  ${r.col} ${r._id} (would create)`);
      continue;
    }
    const doc = { ...r.doc };
    if (r.col === 'useraccounts') {
      // Random password: the engine mints JWTs directly, nobody logs in with it.
      doc.password = await bcrypt.hash(crypto.randomBytes(18).toString('base64'), 10);
    }
    await col(r.col).updateOne({ _id: r._id }, { $setOnInsert: doc }, { upsert: true });
    console.log(`  created  ${r.col} ${r._id}`);
  }
  if (existingPlatform) {
    console.log(`  using existing platform company ${existingPlatform._id} (${existingPlatform.name})`);
  }
  await client.close();

  console.log('\nPut these in automation-testing/.env:');
  console.log(`TEST_BASIC_PLAN_COMPANY_ID=${IDS.basicCompany}`);
  console.log(`TEST_BASIC_PLAN_EMPLOYEE_ID=${IDS.basicEmployee}`);
  if (teamDefaultCompany) {
    console.log('# TEST_BASIC_* left unset: this DB has the team "Top Auto Default" company, the engine default');
  } else {
    console.log(`TEST_BASIC_COMPANY_ID=${IDS.basicCompany}`);
    console.log(`TEST_BASIC_EMPLOYEE_ID=${IDS.basicEmployee}`);
  }
  console.log(`TEST_PREMIUM_COMPANY_ID=${IDS.premiumCompany}`);
  console.log(`TEST_PREMIUM_EMPLOYEE_ID=${IDS.premiumEmployee}`);
  console.log(`TEST_PLATFORM_COMPANY_ID=${platformCompanyId}`);
  console.log(`TEST_PLATFORM_ADMIN_ID=${IDS.platformAdmin}`);
  if (mode === 'dry-run') console.log('\n(dry run: nothing was written; re-run with --apply)');
}

main().catch((err) => {
  console.error('[fixtures] failed:', err.message);
  process.exit(1);
});
