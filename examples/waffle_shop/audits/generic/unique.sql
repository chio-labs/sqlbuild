AUDIT ();

SELECT @column
FROM __ref("@model")
GROUP BY @column
HAVING COUNT(*) > 1
