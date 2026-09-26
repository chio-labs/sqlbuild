Source tapes/common.tape
Output out/quickstart.gif
Output out/quickstart.mp4
Hide
Type "cd scratch/quickstart && export PS1='$ ' && clear"
Enter
Sleep 500ms
Show
Type "sqb playground waffle-shop"
Sleep 300ms
Enter
Sleep 2s
Type "cd waffle-shop"
Enter
Sleep 500ms
Type "sqb build"
Sleep 300ms
Enter
Sleep 8s
Type "sqb test"
Sleep 300ms
Enter
Sleep 6s
Screenshot out/quickstart.png
Sleep 2s
