# Bash completion for iiserb-login-app

_iiserb_login_app_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="login logout status reconnect bounce service logs diag config"
    local global_opts="--gui -g --json -j --quiet -q --short --help -h -l --login -s --status -r --reconnect --logout"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands $global_opts" -- "$cur") )
        return 0
    fi

    case "${words[1]}" in
        service)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "start stop restart status enable disable" -- "$cur") )
            fi
            ;;
        logs)
            COMPREPLY=( $(compgen -W "-n --lines -f --follow" -- "$cur") )
            ;;
        config)
            COMPREPLY=( $(compgen -W "-u --username -p --password --password-stdin --gateway --probe --ping-target --check-interval --keepalive-interval" -- "$cur") )
            ;;
        status)
            COMPREPLY=( $(compgen -W "-j --json -q --quiet --short" -- "$cur") )
            ;;
        login|logout)
            COMPREPLY=( $(compgen -W "-j --json -q --quiet" -- "$cur") )
            ;;
        reconnect|bounce)
            COMPREPLY=( $(compgen -W "-q --quiet" -- "$cur") )
            ;;
        *)
            COMPREPLY=( $(compgen -W "$global_opts" -- "$cur") )
            ;;
    esac
}

complete -F _iiserb_login_app_completion iiserb-login-app
