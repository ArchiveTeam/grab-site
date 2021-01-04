# grab-site
#
# VERSION               0.0.1

FROM  lnl7/nix:2.3.7
ENV   TZ=Etc/UTC
LABEL Description="Install and run the grab-site program via Nix" Vendor="ArchiveTeam/ArchiveBot" Version="0.0.1"
EXPOSE 29000/tcp

RUN nix-env -iA \
	nixpkgs.bash \
	nixpkgs.grab-site

CMD gs-server & \
	grab-site 'https://community.fantasyflightgames.com/'
