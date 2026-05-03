AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column IS NULL
