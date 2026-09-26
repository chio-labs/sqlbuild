Source tapes/common.tape
Set FontSize 16
Set Width 1400
Set Height 1100
Output out/scope.gif
Output out/scope.mp4
Hide
Type "cd scratch/scope && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "find models/marts/_sqlbuild models/marts/daily_revenue.sql -type f"
Enter
Sleep 1500ms
Type "sqb scope model:daily_revenue --as-path models/intermediate/daily_revenue.sql"
Sleep 300ms
Enter
Sleep 5s
Screenshot out/scope.png
Sleep 3s
