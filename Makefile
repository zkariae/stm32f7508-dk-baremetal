# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       Makefile
# \brief      Repository-level targets; everything else goes to firmware/Makefile.
#
# \author     Z. BEN-AKKA
# \version    1.0
# \date       10/10/2026
#
# \details
#   documentation  HTML documentation in work/doc/html (doxygen)
#   format         format the C sources (scripts/format_cxx.sh)
#   Any other target is forwarded, so make 01-blink-flash works from here.
#
# \section root_makefile_version_history Version history
# | Version | Date       | Author      | Description      |
# |:-------:|:----------:|:------------|:-----------------|
# | 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
# ****************************
# */

.DEFAULT_GOAL := help

# Make the documentation from board perspective
.PHONY: documentation
documentation:
	@rm -rf work/doc
	@mkdir -p work/doc
	@doxygen ./scripts/Doxyfile
	@echo "work/doc/html/index.html ($$(wc -l < work/doc/doxygen.warnings) warning lines in work/doc/doxygen.warnings)"

# Format source files
.PHONY: format
format:
	@bash -c "scripts/format_cxx.sh"

# The firmware's help, plus the targets above
.PHONY: help
help:
	@$(MAKE) --no-print-directory -C firmware help
	@echo ""
	@echo "Repository:"
	@echo "  documentation        HTML documentation in work/doc/html (doxygen)"
	@echo "  format               format the sources (scripts/format_cxx.sh)"

# Any other target: hand it to firmware/Makefile
%: FORCE
	@$(MAKE) --no-print-directory -C firmware $@

.PHONY: FORCE
FORCE:

# Without this, make would try to rebuild this Makefile through the rule above
Makefile: ;
