Source tapes/common.tape
Set FontSize 16
Set Width 1400
Set Height 1180
Output out/scope.gif
Output out/scope.mp4
Hide
Type "cd scratch/scope && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "tree --noreport models/marts --prune -P 'daily_revenue.sql|payment_status.sql|*.py'"
Enter
Sleep 1500ms
Type "sqb scope model:daily_revenue --as-path models/intermediate/daily_revenue.sql"
Sleep 300ms
Enter
Wait@60s /\$\s*$/
Sleep 1s
Screenshot out/scope.png
Sleep 15s
