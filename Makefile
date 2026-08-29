APPS := $(patsubst %/,%,$(dir $(wildcard [0-9][0-9]-*/Makefile)))

.DEFAULT_GOAL := help

define app_rules
$(1): ## Build $(1)
	$$(MAKE) -C $(1)

$(1)-flash: ## Flash $(1)
	$$(MAKE) -C $(1) flash

$(1)-clean: ## Clean $(1)
	$$(MAKE) -C $(1) clean
endef

$(foreach app,$(APPS),$(eval $(call app_rules,$(app))))

all:  ## Build every application
	@for app in $(APPS); do $(MAKE) -C $$app || exit 1; done

clean:  ## Clean every application
	@for app in $(APPS); do $(MAKE) -C $$app clean; done

list:  ## List available applications
	@for app in $(APPS); do echo "  $$app"; done

help:  ## Show this help
	@echo "Applications:"
	@for app in $(APPS); do echo "  \033[36m$$app\033[0m          build"; \
	  echo "  \033[36m$$app-flash\033[0m    build and flash"; done
	@echo ""
	@echo "Other targets:"
	@echo "  \033[36mall\033[0m           build everything"
	@echo "  \033[36mclean\033[0m         clean everything"
	@echo "  \033[36mlist\033[0m          list applications"

.PHONY: all clean list help $(APPS)
