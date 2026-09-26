Source tapes/common.tape
Set FontSize 16
Set Width 1480
Set Height 760
Output out/rules.gif
Output out/rules.mp4
Hide
Type "cd scratch/rules && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "sqb compile --select fact_orders"
Sleep 300ms
Enter
Wait@60s /\$\s*$/
Sleep 1s
Screenshot out/rules.png
Sleep 15s
