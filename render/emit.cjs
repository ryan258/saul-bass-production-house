/* Generic frame producer. The project owns artwork and animation. */
const fs=require('node:fs'),path=require('node:path'),{once}=require('node:events');
const opts=JSON.parse(process.argv[2]);
const driver=require(path.resolve(opts.driver)),runtime=require('./runtime.cjs');
async function main(){
 await driver.init();let last='',raw;
 for(let j=0;j<opts.count;j++){
  const n=opts.start+j;
  const svg=opts.shot?driver.shotFrame(opts.shot,n):driver.frame(n);
  if(svg!==last){raw=await runtime.raster(svg,opts.width,opts.height);last=svg;}
  if(raw.length!==opts.width*opts.height*4)throw Error('Driver raster size differs from project config');
  if(!process.stdout.write(raw))await once(process.stdout,'drain');
 }
}
main().catch(e=>{console.error(e);process.exitCode=1});
