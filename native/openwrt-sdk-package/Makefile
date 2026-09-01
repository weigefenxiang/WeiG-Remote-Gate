include $(TOPDIR)/rules.mk

PKG_NAME:=remote-gate-mapper
PKG_VERSION:=$(strip $(shell cat $(TOPDIR)/package/weig-remote-gate-mapper/VERSION 2>/dev/null))
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=WeiG Remote Gate
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk

define Package/remote-gate-mapper
  SECTION:=net
  CATEGORY:=Network
  TITLE:=WeiG Remote Gate native mapped-access helper
endef

define Package/remote-gate-mapper/description
 Small IPv4/UDP mapping and relay helper used by WeiG Remote Gate Mapped Access.
endef

define Build/Prepare
	$(RM) -r $(PKG_BUILD_DIR)
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(CP) $(TOPDIR)/package/weig-remote-gate-mapper/src/remote-gate-mapper.c $(PKG_BUILD_DIR)/remote-gate-mapper.c
endef

define Build/Compile
	$(TARGET_CC) \
		$(TARGET_CFLAGS) \
		$(TARGET_CPPFLAGS) \
		-O2 -static \
		-Wall -Wextra -Werror -Wformat=2 -Wno-error=format-nonliteral \
		-Wshadow -Wconversion -Wstrict-prototypes \
		-std=c11 \
		-o $(PKG_BUILD_DIR)/remote-gate-mapper \
		$(PKG_BUILD_DIR)/remote-gate-mapper.c \
		$(TARGET_LDFLAGS)
endef

define Package/remote-gate-mapper/install
	$(INSTALL_DIR) $(1)/usr/lib/remote-gate
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/remote-gate-mapper $(1)/usr/lib/remote-gate/remote-gate-mapper
endef

$(eval $(call BuildPackage,remote-gate-mapper))
