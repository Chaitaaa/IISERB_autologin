# Fish completion for iiserb-login-app

complete -c iiserb-login-app -f

# Global flags
complete -c iiserb-login-app -s g -l gui -d "Launch GUI"
complete -c iiserb-login-app -s j -l json -d "Output in JSON format"
complete -c iiserb-login-app -s q -l quiet -d "Quiet mode"
complete -c iiserb-login-app -l short -d "Single line summary"
complete -c iiserb-login-app -s h -l help -d "Show help"

# Subcommands
complete -c iiserb-login-app -n "__fish_use_subcommand" -a login -d "Authenticate with portal"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a logout -d "Log out from gateway"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a status -d "Show connection status"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a reconnect -d "Refresh network link"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a bounce -d "Refresh network link"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a service -d "Manage systemd service"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a logs -d "View daemon logs"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a diag -d "Run network diagnostics"
complete -c iiserb-login-app -n "__fish_use_subcommand" -a config -d "Configure credentials"

# Subcommand arguments
complete -c iiserb-login-app -n "__fish_seen_subcommand_from service" -a "start stop restart status enable disable"
complete -c iiserb-login-app -n "__fish_seen_subcommand_from logs" -s f -l follow -d "Follow live logs"
complete -c iiserb-login-app -n "__fish_seen_subcommand_from logs" -s n -l lines -d "Lines to view"
