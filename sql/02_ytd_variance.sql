-- Year-to-date actual vs budget per entity and budget line
WITH actual AS (
    SELECT g.entity, m.budget_line, SUM(g.amount) AS actual
    FROM gl_actuals g
    JOIN account_mapping m ON m.account = g.account
    WHERE g.month <= :through
    GROUP BY g.entity, m.budget_line
),
plan AS (
    SELECT entity, budget_line, SUM(amount) AS budget
    FROM budget
    WHERE month <= :through
    GROUP BY entity, budget_line
)
SELECT p.entity,
       p.budget_line,
       ROUND(p.budget, 1)                                         AS budget,
       ROUND(COALESCE(a.actual, 0), 1)                            AS actual,
       ROUND(COALESCE(a.actual, 0) - p.budget, 1)                 AS variance,
       ROUND(100.0 * (COALESCE(a.actual, 0) - p.budget) / p.budget, 1) AS variance_pct
FROM plan p
LEFT JOIN actual a ON a.entity = p.entity AND a.budget_line = p.budget_line
ORDER BY p.entity, p.budget_line;
