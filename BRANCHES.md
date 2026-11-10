# Branches, Departments & Scoped Admin — what changed and where

## The model

```
Organization (company)                       ← existing tenant, unchanged
 └─ Branch  (unit / subsidiary)              ← NEW  branches
     ├─ Department                           ← NEW  departments (replaces the free-text `dept` label)
     └─ Membership (user ↔ branch [+ dept])  ← NEW  branch_memberships  (role: admin | manager | staff)
categories · items · stock_history · sales · expenses  → each now carries branch_id + department_id
```

Each branch runs its own categories, products, stock, sales and expenses. The company sees all branches
together (collective view) or any one separately.

### Who can do what
| Level | Who | Sees | Can manage |
|---|---|---|---|
| Company | `is_org_admin`, role `admin` / `super_admin` | every branch, collectively or filtered | create/edit/deactivate/delete branches, departments, appoint **branch admins**, assign anyone |
| Branch admin | membership role `admin` | only their branch(es) | their branch's details, departments, manager/staff assignments, void sales, delete expenses/categories |
| Branch manager | membership role `manager` | their branch | categories, expenses, edit sales comments (same powers a manager had, now branch-limited) |
| Staff | membership role `staff` | their branch (own sales only, as before) | record sales / stock / products as before |
| Department-limited | any membership with a department | only that department's data | — |

Existing global roles still gate each endpoint exactly as before; the branch scope is an **additional** limit on top.
Assigning someone as branch admin/manager automatically grants the global `manager` role if they lack it.

## Server — where it applies

**New files**
- `app/models/branch.py` — `Branch`, `Department`, `BranchMembership`
- `app/services/scope_service.py` — `AccessScope` (who) + `ScopeFilter` (which rows) + `apply_scope()` — the single enforcement point
- `app/services/branch_service.py` — branch/department/membership logic, `ensure_default_branch()`
- `app/api/deps/scope.py` — `get_access_scope`, `get_scope_filter` dependencies
- `app/api/v1/branches.py`, `app/api/v1/departments.py` — new endpoints (registered in `router.py`)
- `app/schemas/branch.py`
- `alembic_versions_to_add/20261031_add_branches_departments.py` — migration (see below)

**Modified**
- `models/{category,items,stock_history,sales,expenses}.py` — `branch_id`, `department_id` (+ in `get_summary`)
- `services/inventory_service.py` — every list/get takes `scope=`; create paths set branch/department; category must be in the item's branch
- `services/report_service.py` — `get_report`/`get_product_detail_report` take `scope=`; new `get_breakdown_report()`
- `api/v1/{categories,items,stock,sales,expenses,reports}.py` — every endpoint scoped; destructive actions need branch-admin
- `api/v1/auth.py`, `schemas/auth.py` — new org gets a default branch at signup; created/public-signup users get a branch assignment
- `schemas/inventory.py` — optional `branch_id` / `department_id` on create/update

**Integrity rules enforced server-side**
- Sales & stock entries take branch/department **from the item**, never from the client.
- Items/categories can't move between branches; a category can only serve items of its own branch.
- Cross-branch ids return 404/403; cross-organization ids return 404.
- Staff never see another branch's data, even by guessing ids.

## API additions
```
GET    /branches/me                          scope for the switcher (branches, my role, departments)
GET/POST   /branches                         list / create [org admin]
GET/PUT/DELETE /branches/{id}                delete only if the branch holds no data
GET    /branches/{id}/members                [org admin / branch admin]
POST   /branches/{id}/members                assign {user_id, role, department_id?}
DELETE /branches/{id}/members/{membership_id}
GET    /branches/{id}/assignable-users
GET/POST /departments ; PUT/DELETE /departments/{id}
GET    /reports/breakdown?group_by=branch|department&period=…&branch_id=…   side-by-side comparison
```
All read endpoints accept optional `?branch_id=` and `?department_id=`. Omit them for the collective view
of everything the caller may access. `/reports` now also honours `start`/`end` (custom range).

## Client — where it applies
- `context/BranchContext.tsx` (+ `<BranchProvider>` in `App.tsx`) — available branches, active selection (remembered per user)
- `services/scopeStore.ts` — makes every list/report call automatically scoped; pages re-fetch on `scopeKey`
- `components/branch/BranchSwitcher.tsx` — topbar (desktop) / top of page (mobile); also in Reports filters
- `components/branch/BranchDeptSelect.tsx` — branch + department pickers in Product, Category, Expense and Create-User forms
- `components/branch/BranchBreakdown.tsx` — branch (or department) comparison table inside **Reports**
- `pages/branches/Branches.tsx` — new **Branches & Teams** page (`/branches`, sidebar + route)
- Updated: `Dashboard`, `Inventory`, `Categories`, `StockIn`, `Sales`, `Expenses`, `Reports`, `Users` (create-user branch fields), `MainLayout`, `types`, `InventoryService`

## Round 2 — UI consistency & responsiveness
**New shared pieces** (`client/src`)
- `components/ui/SearchableSelect.tsx` — searchable dropdown used for *every* selection (branch/department switcher, product, category, parent category, roles, plans, months/years, users). Menu renders in a portal so cards/modals/drawers never clip it.
- `components/ui/SideDrawer.tsx` — slide-in panel. Used instead of long inline cards on small screens: Reports filters, Stock-In receive form, Expenses form, Branch details.
- `components/ui/ConfirmProvider.tsx` (`useConfirm().confirm / prompt`, mounted in `App.tsx`) — themed replacement for every `window.confirm` / `prompt` (Organizations, Settings, Categories, Branches). No native alerts remain.
- `components/branch/BranchBadge.tsx` — shows which branch (and role) you work in: sidebar footer, topbar, user menu, dashboard header, and top of page on mobile. Staff in one branch always see theirs.
- `hooks/useMediaQuery.ts`, `styles/responsive.css` (imported in `main.tsx`) — stat-card/icon shrinking on phones, drawer, select and Branches-page styles.

**Behaviour changes**
- **Departments come from one source**: the branch's department list (managed on *Branches*). Free-text department inputs are removed from Products, Categories, Expenses and Sales. A branch with one department auto-selects it; with several, the server requires a choice (`resolve_write_target(require_department=True)`, `create_item`). Sales take their department from the product. Sales' department filter is a dropdown.
- **Reports category filter** is applied server-side (`GET /reports?category_id=`, includes sub-categories, 404 if outside your scope) and reloads automatically on change. Expenses aren't tied to categories, so they are left out in category view (a note is shown; response field `expenses_excluded_by_category`).
- **Stock In**: searchable product picker (name / SKU, with stock count) and broader history search (product, reference, notes, recorded-by).
- **Dashboard / Reports cards**: fluid values and smaller icons at ≤767px / ≤575px.
- **/branches** restyled to the app theme (`content-card`, `imf-table`, header/badge/button styles, `#344767` headings).

## Deploying (in this order)
1. Copy `alembic_versions_to_add/20261031_add_branches_departments.py` into your `alembic/versions/`, set `down_revision`
   to your current head (`alembic heads`), then `alembic upgrade head`. Needs PostgreSQL 13+.
2. Deploy the server, then the client.

**What the migration does to existing data:** one *Main Branch* (code `HQ`) per organization; each distinct legacy `dept`
text becomes a Department of it; all existing categories/items/stock/sales/expenses are attached to it; every non-admin user
is assigned to it (manager→manager, others→staff). Org owners/admins need nothing. The migration is re-runnable and has a downgrade.
The new columns stay nullable so old and new app instances can run side by side during a rolling deploy.

## Verified
- ~50 API assertions against PostgreSQL 16 (scoping, cross-branch/org isolation, branch-admin limits, department-limited users, reports/breakdown totals, delete guards).
- Migration run on a database built from your original models: 0 unassigned rows, idempotent re-run, downgrade/upgrade round trip.
- TypeScript: no new errors (only pre-existing unused-variable warnings remain). Backend suite re-run after round 2 (department auto-select/required rules, report `category_id`): all pass.
- Not run: the UI in a browser (the zip has no `package.json`/Vite config), and `main.py` (not in the zip). Please smoke-test the screens.
