# Operate the LiteLLM gateway.
#   Edit models.yaml (models + per-model regions) and/or .env, then:  make up
#   The container regenerates generated/config.yaml on every start.

.PHONY: up restart stop down logs config models ps test

up:        ## render + start everything
	docker compose up -d

restart:   ## regenerate config + restart the proxy (after editing models.yaml/.env)
	docker compose restart litellm

stop:      ## stop containers (keeps data)
	docker compose stop

down:      ## remove containers (keeps the db volume)
	docker compose down

logs:      ## follow proxy logs (includes the [render] output)
	docker compose logs -f litellm

config:    ## show the rendered config LiteLLM actually loaded
	@cat generated/config.yaml

models:    ## list the model names the proxy is serving
	@grep 'model_name:' generated/config.yaml

ps:        ## container status
	docker compose ps
