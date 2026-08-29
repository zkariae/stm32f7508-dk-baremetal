APPS := $(patsubst %/,%,$(dir $(wildcard [0-9][0-9]-*/Makefile)))

MAKE_APP = $(MAKE) --no-print-directory -C

.DEFAULT_GOAL := help

####################################################################
# Per-application rules, generated from the folders found above
####################################################################

define app_rules
.PHONY: $(1)
$(1): ## Build $(1)
	$$(MAKE_APP) $(1)

.PHONY: $(1)-flash
$(1)-flash: ## Build and flash $(1)
	$$(MAKE_APP) $(1) flash

.PHONY: $(1)-clean
$(1)-clean: ## Clean $(1)
	$$(MAKE_APP) $(1) clean
endef

$(foreach app,$(APPS),$(eval $(call app_rules,$(app))))

####################################################################
# Across all applications
####################################################################

.PHONY: all
all:  ## Build every application
	@for app in $(APPS); do $(MAKE_APP) $$app || exit 1; done

.PHONY: clean
clean:  ## Clean every application
	@for app in $(APPS); do $(MAKE_APP) $$app clean; done

.PHONY: list
list:  ## List available applications
	@for app in $(APPS); do echo "  $$app"; done

.PHONY: help
help:  ## Show this help
	@echo "Targets:"
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Applications found: $(APPS)"
