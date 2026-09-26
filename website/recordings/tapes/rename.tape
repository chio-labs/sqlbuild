Source tapes/common.tape
Output out/rename.gif
Output out/rename.mp4
Hide
Type "cd scratch/rename && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "find models -name '*.sql'"
Enter
Sleep 1500ms
Type "mkdir models/finance && mv models/marts/revenue.sql models/finance/daily_revenue.sql"
Sleep 300ms
Enter
Sleep 800ms
Type "sqb plan"
Sleep 300ms
Enter
Sleep 5s
Screenshot out/rename.png
Sleep 3s
