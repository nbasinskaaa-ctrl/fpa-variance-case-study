-- Monthly actuals with running YTD total and month-over-month change
WITH monthly AS (
    SELECT g.entity, m.budget_line, g.month, SUM(g.amount) AS actual
    FROM gl_actuals g
    JOIN account_mapping m ON m.account = g.account
    WHERE g.month <= :through
    GROUP BY g.entity, m.budget_line, g.month
)
SELECT entity,
       budget_line,
       month,
       ROUND(actual, 1) AS actual,
       ROUND(SUM(actual) OVER (PARTITION BY entity, budget_line ORDER BY month), 1) AS actual_ytd,
       ROUND(actual - LAG(actual) OVER (PARTITION BY entity, budget_line ORDER BY month), 1) AS mom_change
FROM monthly
ORDER BY entity, budget_line, month;
