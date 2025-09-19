#!/bin/bash
# Bootstrap script that either sets up a fresh XDMoD test instance or upgrades
# an existing one.  This code is only designed to work inside the XDMoD test
# docker instances. However, since it is designed to test a real install, the
# set of commands that are run would work on a real production system.

BASEDIR=/root/xdmod-nairr/scripts
REF_SOURCE=$(realpath $BASEDIR/../tests/artifacts/nairr)
XDMOD_SRC_DIR=$(realpath ${XDMOD_SRC_DIR:-$BASEDIR/../xdmod})
REPODIR=$(realpath $XDMOD_SRC_DIR)
REF_DIR=/var/tmp/nairr
BUILD_DIR=$(realpath $XDMOD_SRC_DIR/open_xdmod/build)
PREFIX="/opt/xdmod"

function copy_template_httpd_conf {
  cp /opt/xdmod/share/templates/apache.conf /etc/httpd/conf.d/xdmod.conf
}

function move_info_etc_xdmod {

  rm /opt/xdmod/etc/organization.json
  rm /opt/xdmod/etc/resource_specs.json
  rm /opt/xdmod/etc/resources.json
  rm /opt/xdmod/etc/resource_types.json
  rm /opt/xdmod/etc/hierarchy.json
  # Copy the reference data into the /etc/xdmod directory. This is where the
  cp $REF_SOURCE/organization.json /opt/xdmod/etc/
  cp $REF_SOURCE/resource_specs.json /opt/xdmod/etc/
  cp $REF_SOURCE/resources.json /opt/xdmod/etc/
  cp $REF_SOURCE/resource_types.json /opt/xdmod/etc/
  cp $REF_SOURCE/hierarchy.json /opt/xdmod/etc/
}

function copy_reports {
  mkdir /opt/xdmod/reports
  cp -r /root/reports/* /opt/xdmod/reports/
  chmod 770 /opt/xdmod/reports
  chown -R apache:xdmod /opt/xdmod/reports
}

if [ -z $XDMOD_REALMS ]; then
  export XDMOD_REALMS=jobs,storage,cloud,resourcespecifications
fi

cp -r $REF_SOURCE /var/tmp/

set -e
set -o pipefail

PYTHON_SCIPY=python3-scipy
if [ $(rpm -E %{rhel}) = 7 ]; then
  PYTHON_SCIPY=python36-scipy
fi

# Install python dependencies for the image hash comparison algorithm
yum install -y python3 python3-six python3-numpy python3-pillow ${PYTHON_SCIPY}
pip3 install imagehash==4.2.1
cp $XDMOD_SRC_DIR/tests/ci/scripts/imagehash /root/bin

# nairr dependencies
yum install -y --enablerepo "powertools" python3-matplotlib python3-pandas ${PYTHON_SCIPY}

# ensure php error logging is set to E_ALL (recommended setting for development)
sed -i 's/^error_reporting = .*/error_reporting = E_ALL/' /etc/php.ini

# ensure php command-line errors are logged to a file
sed -i 's/^;error_log = php_errors.log/error_log = \/var\/log\/php_errors.log/' /etc/php.ini

echo 'export PATH="/opt/xdmod/bin:$PATH"' | sudo tee /etc/profile.d/xdmod.sh
sudo chmod +x /etc/profile.d/xdmod.sh

source /etc/profile.d/xdmod.sh

if [ "$XDMOD_TEST_MODE" = "fresh_install" ]; then
  rpm -qa | grep ^xdmod | xargs yum -y remove || true
  rm -rf /etc/xdmod

  rm -rf /var/lib/mysql
  mkdir -p /var/lib/mysql
  mkdir -p /var/log/mariadb
  mkdir -p /var/run/mariadb
  chown -R mysql:mysql /var/lib/mysql
  chown -R mysql:mysql /var/log/mariadb
  chown -R mysql:mysql /var/run/mariadb

  dnf install -y php-pgsql mod_ssl

  #Install XDMOD and Modules

  # Install XDMOD and Modules
  for dir in "$BUILD_DIR"/*/; do
    cd "$dir" || continue
    ./install --prefix="$PREFIX"
    cd - >/dev/null
  done

  mysql_install_db --user mysql

  if [ -f /etc/my.cnf.d/mariadb-server.cnf ]; then
    >/etc/my.cnf.d/mariadb-server.cnf
    echo "# this is read by the standalone daemon and embedded servers
              [server]
              sql_mode=
              # this is only for the mysqld standalone daemon
              # Settings user and group are ignored when systemd is used.
              # If you need to run mysqld under a different user or group,
              # customize your systemd unit file forsource /etc/profile.d/xdmod.sh source /etc/profile.d/xdmod.shmysqld/mariadb according to the
              # instructions in http://fedoraproject.org/wiki/Systemd
              [mysqld]
              datadir=/var/lib/mysql
              socket=/var/lib/mysql/mysql.sock
              log-error=/var/log/mariadb/mariadb.log
              pid-file=/run/mariadb/mariadb.pid" >/etc/my.cnf.d/mariadb-server.cnf
  fi
  move_info_etc_xdmod
  copy_template_httpd_conf

  if [ -d "/root/reports" ]; then
    copy_reports
  fi

  # Download patch directly to /tmp (no cd)
  #
  # This patch is a most install patch for xdmod-nairr that
  # Adds new resource type for Program
  curl -o /tmp/1942.patch https://patch-diff.githubusercontent.com/raw/ubccr/xdmod/pull/1942.patch

  # Apply the patch in /usr/share/xdmod without changing directory
  patch -d /opt/xdmod/share -p1 </tmp/1942.patch

  ~/bin/services start
  mysql -e "CREATE USER 'root'@'gateway' IDENTIFIED BY '';
    GRANT ALL PRIVILEGES ON *.* TO 'root'@'gateway' WITH GRANT OPTION;
    FLUSH PRIVILEGES;"

  # TODO: Replace diff files with hard fixes
  # Modify integration sso tests to work with cloud realm
  if [ "$XDMOD_REALMS" = "cloud" ]; then
    if ! patch --dry-run -Rfsup1 --directory=$REPODIR <$XDMOD_SRC_DIR/tests/ci/diff/SSOLoginTest.php.diff >/dev/null; then
      # -- Fix users searched in SSO test
      patch -up1 --directory=$REPODIR <$XDMOD_SRC_DIR/tests/ci/diff/SSOLoginTest.php.diff
    fi
  else
    if patch --dry-run -Rfsup1 --directory=$REPODIR <$XDMOD_SRC_DIR/tests/ci/diff/SSOLoginTest.php.diff >/dev/null; then
      # -- Reverse previous patch
      patch -R -up1 --directory=$REPODIR <$XDMOD_SRC_DIR/tests/ci/diff/SSOLoginTest.php.diff
    fi
  fi

  expect $XDMOD_SRC_DIR/tests/ci/scripts/xdmod-setup-start.tcl | col -b

  mysql -e "CREATE DATABASE modw_resourceactions"
  mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'gateway' WITH GRANT OPTION;
    GRANT ALL PRIVILEGES ON *.* TO 'xdmod'@'gateway' WITH GRANT OPTION;
    FLUSH PRIVILEGES;"

  chmod 770 /opt/xdmod/logs
  chown apache:xdmod /opt/xdmod/logs
  touch /opt/xdmod/logs/exceptions.log
  chmod 660 /opt/xdmod/logs/exceptions.log
  chown apache:xdmod /opt/xdmod/logs/exceptions.log
  touch /opt/xdmod/logs/query.log
  chmod 660 /opt/xdmod/logs/query.log
  chown apache:xdmod /opt/xdmod/logs/query.log

  /opt/xdmod/share/tools/etl/etl_overseer.php -a xdmod.hpcdb-ingest-common.unknown_organization
  xdmod-import-csv -t hierarchy -i $REF_DIR/hierarchy.csv
  xdmod-import-csv -t group-to-hierarchy -i $REF_DIR/group-to-hierarchy.csv

  last_modified_start_date=$(date +'%F %T')

  if [[ "$XDMOD_REALMS" == *"jobs"* ]]; then
    sudo -u xdmod /opt/xdmod/bin/xdmod-shredder -r NVIDIA-DGX-Cloud -f slurmjson -d $REF_DIR/data/dgx/postprocessed/ -q

    sudo -u xdmod /opt/xdmod/bin/xdmod-ingestor
  fi

  if [[ "$XDMOD_REALMS" == *"cloud"* ]]; then

    sudo -u xdmod /opt/xdmod/bin/xdmod-shredder -r Indiana-Jetstream2-GPU -f openstack -d $REF_DIR/data/jetstream/nairr-jetstream2
    sudo -u xdmod /opt/xdmod/bin/xdmod-shredder -r Indiana-Jetstream2-GPU -f openstack -d $REF_DIR/data/jetstream/nairr-jetstream2-lm/
    sudo -u xdmod /opt/xdmod/bin/xdmod-shredder -r Indiana-Jetstream2-GPU -f openstack -d $REF_DIR/data/jetstream/nairr-jetstream2-gpu/

  fi

  echo "Nairr Bootstraping Complete"
  sudo -u xdmod /opt/xdmod/share/tools/etl/etl_overseer.php -p nairr.resource-actions-bootstrap
  sudo -u xdmod /opt/xdmod/share/tools/etl/etl_overseer.php -p nairr.resource-actions -m 2000-01-01
  sudo -u xdmod /opt/xdmod/bin/xdmod-build-filter-lists --realm ResourceActions --quiet

  echo "Nairr Bootstraping Complete"

  echo "Starting XDMoD Ingestor"
  sudo -u xdmod /opt/xdmod/bin/xdmod-ingestor
  echo "XDMoD Ingestor Completed"

  echo "Loading CLoud TO PI Data"
  sudo -u xdmod /opt/xdmod/bin/xdmod-import-csv -t cloud-project-to-pi -i $REF_DIR/cloud-project-to-pi.csv

  sudo -u xdmod /opt/xdmod/bin/xdmod-ingestor --datatype openstack
  sudo -u xdmod /opt/xdmod/bin/xdmod-ingestor --aggregate=cloud --last-modified-start-date "$last_modified_start_date"

  echo "Creating XDMoD Users"
  sudo -u xdmod /opt/xdmod/bin/xdmod-import-csv -t names -i $REF_DIR/names.csv

  sudo -u xdmod /opt/xdmod/bin/xdmod-ingestor

  echo "Creating XDMOD additional users"

  php $XDMOD_SRC_DIR/tests/ci/scripts/create_xdmod_users.php -x /opt/xdmod/share

  echo "XDMoD Bootstraping Complete"

fi
