/* Low-resolution source sampling, separate from production and baseline paths. */
const fs=require('node:fs'),path=require('node:path'),{once}=require('node:events');
const opts=JSON.parse(process.argv[2]);
const driver=require(path.resolve(opts.driver)),{sharp}=require('./runtime.cjs');
async function main(){
 await driver.init();
 if(opts.mode==='stills'){
  for(const item of opts.frames){
   await sharp(Buffer.from(driver.frame(item.frame))).resize(opts.width,opts.height).png().toFile(item.file);
  }
 }else{
  let last='',raw;
  for(let j=0;j<opts.count;j++){
   const svg=driver.frame(opts.start+j);
   if(svg!==last){
    raw=await sharp(Buffer.from(svg)).resize(opts.width,opts.pictureHeight).flatten({background:'#15283f'})
     .extend({top:opts.bannerHeight,bottom:0,left:0,right:0,background:'#15283f'})
     .composite([{input:opts.banner,top:0,left:0}]).removeAlpha().raw().toBuffer();last=svg;
   }
   if(raw.length!==opts.width*opts.height*3)throw Error('Draft raster size mismatch');
   if(!process.stdout.write(raw))await once(process.stdout,'drain');
  }
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
