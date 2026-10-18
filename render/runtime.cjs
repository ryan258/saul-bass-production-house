const path=require('node:path');
let sharp;try{sharp=require('sharp');}catch(error){
 if(!process.env.SBPH_NODE_MODULES)throw Error('sharp is not installed: run npm ci --ignore-scripts, or set SBPH_NODE_MODULES to a node_modules folder that contains it');
 sharp=require(path.join(process.env.SBPH_NODE_MODULES,'sharp'));}
sharp.concurrency(2);
async function raster(svg,width,height){const {data,info}=await sharp(Buffer.from(svg)).ensureAlpha().raw().toBuffer({resolveWithObject:true});if(info.width!==width||info.height!==height||info.channels!==4)throw Error('Raster contract mismatch');return data;}
async function webpTransport(pathname){return 'data:image/png;base64,'+(await sharp(pathname).png().toBuffer()).toString('base64');}
module.exports={sharp,raster,webpTransport};
