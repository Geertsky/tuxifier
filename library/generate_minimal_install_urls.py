#!/usr/bin/python
import dnf
import os,sys
distributionrepourltype=sys.argv[1]
distributionrepourl=sys.argv[2]
packages=sys.argv[3:]
print("distrourl:", distributionrepourltype)
print("distrourl:", distributionrepourl)
print("packages:", packages)
base = dnf.Base()
conf = base.conf 
conf.set_or_append_opt_value('reposdir','/tmp/rocky8-reposdir')
conf.set_or_append_opt_value('installroot','/tmp/rocky8-root')
conf.substitutions['releasever']='8'
conf.substitutions['arch']='x86_64'
conf.substitutions['basearch']='x86_64'
if distributionrepourltype == "metalink":
    base.repos.add_new_repo('BaseOS', conf, metalink=distributionrepourl)
elif distributionrepourltype == mirrorlist:
    base.repos.add_new_repo('BaseOS', conf, mirrorlist=distributionrepourl)
elif distributionrepourltype == baseurl:
    base.repos.add_new_repo('BaseOS', conf, baseurl=distributionrepourl)
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
