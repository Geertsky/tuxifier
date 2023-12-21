#!/usr/bin/python
import dnf
import os
base = dnf.Base()
conf = base.conf 
conf.read('/home/geert/git/geertsky/dracut-bambini/Rocky-BaseOS.repo') 
conf.set_or_append_opt_value('reposdir','/tmp/rocky8-reposdir')
conf.set_or_append_opt_value('installroot','/tmp/rocky8-root')
conf.substitutions['releasever']='8'
conf.substitutions['arch']='x86_64'
conf.substitutions['basearch']='x86_64'
base.repos.add_new_repo('BaseOS', conf,metalink='https://mirrors.rockylinux.org/metalink?arch=$basearch&repo=BaseOS-$releasever&country=ch')
for d in ['/tmp/rocky8-reposdir','/tmp/rocky8-root']:
    try:
        os.mkdir(d)
    except FileExistsError:
        continue
base.read_all_repos() 
base.fill_sack()
base.read_comps(arch_filter=True)
group=base.comps.group_by_pattern("Core")
base.group_install(group.id, ['mandatory', 'default'])
base.resolve()

def get_remote_location(pkg):
    return pkg.remote_location()

urls=map(get_remote_location, list(base.transaction.install_set))
urls_formatted=" ".join(list(urls))
print(urls_formatted)
