Output demo/abox-proof.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 800
Set Theme "Dracula"
Set TypingSpeed 40ms

Type "export PATH=$HOME/.local/bin:$PATH && export KUBECONFIG=~/.kube/config"
Enter
Sleep 500ms

Type "kubectl get nodes"
Enter
Sleep 2s

Type "kubectl get pods -A"
Enter
Sleep 3s

Type "kubectl get gateway,httproute -A"
Enter
Sleep 2s

Type "kubectl get agents -n kagent"
Enter
Sleep 2s

Type "kubectl get svc -n phoenix"
Enter
Sleep 2s

Type "echo 'abox cluster is up and running'"
Enter
Sleep 2s
