// const path = require('path')
// const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin

// Typhon : le build est servi sous /bim-viewer/ (via le dev server Vite du
// front principal, ou copié dans son dist en production). Sans publicPath,
// les assets seraient référencés en absolu à la racine (" /js/...").
// Surchargeable pour servir ailleurs (ex. BIM_VIEWER_BASE=/).
module.exports = {
  publicPath: process.env.BIM_VIEWER_BASE || "/bim-viewer/",
  css: {
    requireModuleExtension: true
  },
  configureWebpack: () => ({
    output: {
      // Node 24 a retiré l'algorithme md4 du provider crypto d'OpenSSL ;
      // webpack 4 (vue-cli 4.5) l'utilisait pour ses contenthash et le build
      // plantait sur "createHash is not a function". sha256 est supporté par
      // webpack 4 et résout le build sur Node >= 17.
      hashFunction: "sha256"
    },
    resolve: {
      alias: {
      }
    },
    // Add package anylyze plugins
    // plugins: [new BundleAnalyzerPlugin()]
    optimization: {
      splitChunks: {
        cacheGroups: {
          common: {
            name: "chunk-common",
            chunks: "initial",
            minChunks: 2,
            maxInitialRequests: 5,
            minSize: 0,
            priority: 1,
            reuseExistingChunk: true,
            enforce: true
          },
          vendors: {
            name: "chunk-vendors",
            test: /[\\/]node_modules[\\/]/,
            chunks: "initial",
            priority: 2,
            reuseExistingChunk: true,
            enforce: true
          },
          elementUI: {
            name: "chunk-elementui",
            test: /[\\/]node_modules[\\/]element-ui[\\/]/,
            chunks: "all",
            priority: 3,
            reuseExistingChunk: true,
            enforce: true
          },
          threejs: {
            name: "chunk-threejs",
            test: /[\\/]three[\\/]/,
            chunks: "all",
            priority: 4,
            reuseExistingChunk: true,
            enforce: true
          },
          public: {
            name: "chunk-public",
            test: /[\\/]public[\\/]/,
            chunks: "all",
            priority: 4,
            reuseExistingChunk: true,
            enforce: true
          }
        }
      }
    },
    devServer: {
      disableHostCheck: true
    }
  })
};
