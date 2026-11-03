const {readdirSync}=require('node:fs');
const {execFileSync}=require('node:child_process');
for(const dir of ['web','extension','tests','scripts']){
  for(const file of readdirSync(dir)){
    if(/\.(c?js)$/.test(file))execFileSync(process.execPath,['--check',`${dir}/${file}`],{stdio:'inherit'});
  }
}
