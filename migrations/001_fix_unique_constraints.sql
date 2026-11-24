-- Fix two constraints that break normal circulation.
--
-- 1. loans: UNIQUE (copy_id, status) means a copy can only ever have ONE 'Returned' loan,
--    so the second return of any copy fails. What we actually want is: at most one
--    *active* (Issued/Overdue) loan per copy.
-- 2. reservations: UNIQUE (book_id, member_id, status) means a member can only cancel
--    (or have fulfilled) a reservation for the same book once. We want: at most one
--    *pending* reservation per member per book.
--
-- Run with:  psql "$DATABASE_URL" -f migrations/001_fix_unique_constraints.sql
-- Safe to run more than once. Runs in a single transaction.

BEGIN;

ALTER TABLE loans DROP CONSTRAINT IF EXISTS uq_active_loan;
CREATE UNIQUE INDEX IF NOT EXISTS uq_loans_active_copy
    ON loans (copy_id)
    WHERE status IN ('Issued', 'Overdue');

ALTER TABLE reservations DROP CONSTRAINT IF EXISTS uq_active_reservation;
CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_pending
    ON reservations (book_id, member_id)
    WHERE status = 'Pending';

-- Indexes for the hot query paths of the API.
CREATE INDEX IF NOT EXISTS ix_loans_member_status ON loans (member_id, status);
CREATE INDEX IF NOT EXISTS ix_loans_due_date_active ON loans (due_date) WHERE status IN ('Issued', 'Overdue');
CREATE INDEX IF NOT EXISTS ix_book_copies_book ON book_copies (book_id);
CREATE INDEX IF NOT EXISTS ix_fines_member_unpaid ON fines (member_id) WHERE is_paid IS NOT TRUE;
CREATE INDEX IF NOT EXISTS ix_reservations_book_pending ON reservations (book_id) WHERE status = 'Pending';

COMMIT;
