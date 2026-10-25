-- Largest cost overrun (in % of budget) per entity, year-to-date
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
      AND budget_line <> 'Revenue'
    GROUP BY entity, budget_line
),
ranked AS (
    SELECT p.entity,
           p.budget_line,
           COALESCE(a.actual, 0) - p.budget                            AS variance,
           100.0 * (COALESCE(a.actual, 0) - p.budget) / p.budget       AS variance_pct,
           RANK() OVER (PARTITION BY p.entity
                        ORDER BY (COALESCE(a.actual, 0) - p.budget) / p.budget DESC) AS rnk
    FROM plan p
    LEFT JOIN actual a ON a.entity = p.entity AND a.budget_line = p.budget_line
)
SELECT entity,
       budget_line,
       ROUND(variance, 1)     AS variance,
       ROUND(variance_pct, 1) AS variance_pct
FROM ranked
WHERE rnk = 1
ORDER BY variance_pct DESC;
