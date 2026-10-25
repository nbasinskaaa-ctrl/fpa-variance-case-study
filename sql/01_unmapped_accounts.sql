-- Data quality: GL accounts with postings but no budget-line mapping
SELECT g.account,
       g.entity,
       COUNT(*)              AS postings,
       ROUND(SUM(g.amount), 1) AS amount
FROM gl_actuals g
LEFT JOIN account_mapping m ON m.account = g.account
WHERE m.account IS NULL
GROUP BY g.account, g.entity
ORDER BY amount DESC;
