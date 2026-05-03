AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column NOT IN (@'values')
